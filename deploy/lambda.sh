#!/usr/bin/env bash
# Deploy the API and the docs site as two arm64 container Lambdas with public Function URLs.
# Re-runnable: creates what's missing, otherwise pushes new images. Needs Docker and the AWS CLI.
#   AWS=aws2 ./deploy/lambda.sh        # AWS defaults to "aws"
set -euo pipefail
cd "$(dirname "$0")/.."

AWS=${AWS:-aws}
REGION=${REGION:-$($AWS configure get region)}
ACCOUNT=$($AWS sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
ROLE=fuel-route-lambda
TAG=$(git rev-parse --short HEAD)
export AWS_REGION=$REGION AWS_PAGER=""

$AWS ecr get-login-password | docker login -u AWS --password-stdin "$REGISTRY" >/dev/null

if ! ROLE_ARN=$($AWS iam get-role --role-name $ROLE --query Role.Arn --output text 2>/dev/null); then
  ROLE_ARN=$($AWS iam create-role --role-name $ROLE --query Role.Arn --output text --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}')
  $AWS iam attach-role-policy --role-name $ROLE --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  sleep 10  # a brand-new role isn't assumable by Lambda straight away
fi

# deploy NAME IMAGE CONFIG_ARGS... -> prints the Function URL. CONFIG_ARGS apply on create and on every update.
deploy() {
  local name=$1 image=$2; shift 2
  $AWS ecr describe-repositories --repository-names "$name" >/dev/null 2>&1 ||
    $AWS ecr create-repository --repository-name "$name" >/dev/null
  docker push -q "$image" >/dev/null

  if $AWS lambda get-function --function-name "$name" >/dev/null 2>&1; then
    $AWS lambda update-function-code --function-name "$name" --image-uri "$image" >/dev/null
    $AWS lambda wait function-updated-v2 --function-name "$name"
    $AWS lambda update-function-configuration --function-name "$name" --timeout 30 "$@" >/dev/null
  else
    $AWS logs create-log-group --log-group-name "/aws/lambda/$name" 2>/dev/null || true
    $AWS logs put-retention-policy --log-group-name "/aws/lambda/$name" --retention-in-days 7
    $AWS lambda create-function --function-name "$name" --package-type Image --code ImageUri="$image" \
      --role "$ROLE_ARN" --architectures arm64 --timeout 30 "$@" >/dev/null
    $AWS lambda wait function-active-v2 --function-name "$name"
    $AWS lambda create-function-url-config --function-name "$name" --auth-type NONE >/dev/null
    # Public URL: both permissions are required for AuthType NONE.
    $AWS lambda add-permission --function-name "$name" --statement-id url --principal '*' \
      --action lambda:InvokeFunctionUrl --function-url-auth-type NONE >/dev/null
    $AWS lambda add-permission --function-name "$name" --statement-id invoke --principal '*' \
      --action lambda:InvokeFunction >/dev/null
  fi
  $AWS lambda wait function-updated-v2 --function-name "$name"
  $AWS lambda get-function-url-config --function-name "$name" --query FunctionUrl --output text
}

# Lambda rejects multi-manifest images, hence --provenance=false.
API_IMAGE=$REGISTRY/fuel-route-api:$TAG
docker build --platform linux/arm64 --provenance=false -t "$API_IMAGE" api
# Lambda sends one request at a time per instance: 1 worker boots twice as fast as the image's 2.
API_URL=$(deploy fuel-route-api "$API_IMAGE" --memory-size 3008 \
  --image-config '{"Command":["gunicorn","config.wsgi","-b","0.0.0.0:8000","-w","1","--threads","4","-k","gthread","--access-logfile","-"]}' \
  --environment "Variables={DEBUG=0,SECRET_KEY=$(openssl rand -hex 32),ALLOWED_HOSTS=.lambda-url.$REGION.on.aws\,127.0.0.1,\
CACHE_DIR=/tmp/cache,AWS_LWA_PORT=8000,AWS_LWA_READINESS_CHECK_PATH=/api/openapi.yaml}")

# The docs site proxies /api/* to the API (docs/app/api/[...path]/route.ts reads API_ORIGIN per request).
# SITE_URL is only known once the docs function exists, so the first deploy's OG images point at localhost.
SITE_URL=$($AWS lambda get-function-url-config --function-name fuel-route-docs --query FunctionUrl --output text 2>/dev/null || true)
DOCS_IMAGE=$REGISTRY/fuel-route-docs:$TAG
docker build --platform linux/arm64 --provenance=false -t "$DOCS_IMAGE" --build-context api=api \
  --build-arg SITE_URL="${SITE_URL%/}" docs
DOCS_URL=$(deploy fuel-route-docs "$DOCS_IMAGE" --memory-size 1024 \
  --environment "Variables={API_ORIGIN=${API_URL%/},AWS_LWA_PORT=3000}")

# The first cold start after a deploy lazy-loads the image (~14 s); take it here, not on a reviewer's first click.
curl -s -o /dev/null "${DOCS_URL}api/route/?start=Dallas,%20TX&finish=Chicago,%20IL"

echo "API:  ${API_URL}api/route/?start=Dallas,%20TX&finish=Chicago,%20IL"
echo "Docs: ${DOCS_URL}docs"
