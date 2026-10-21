// Mirrors RoutePlan / FuelStop / Error in api/openapi.yaml.
export interface Place {
  query: string;
  lat: number;
  lon: number;
}

export interface FuelStop {
  mile: number;
  name: string;
  address: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
  price: number;
  gallons: number;
  cost: number;
}

export interface RoutePlan {
  start: Place;
  finish: Place;
  distance_miles: number;
  duration_hours: number;
  fuel_stops: FuelStop[];
  total_gallons_purchased: number;
  total_fuel_cost: number;
  cost_of_fuel_consumed: number | null;
  stop_penalty: number;
  route: { type: 'LineString'; coordinates: number[][] };
  map_url: string;
  external_api_calls: number;
}

export interface ApiError {
  error: string;
  detail?: string;
}
