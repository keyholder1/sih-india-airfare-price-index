/**
 * News / event context — from `GET /api/v1/routes/{route}/context`
 * (api/routes/news.py). Backed by NewsContextService + MockNewsProvider;
 * see src/index_engine/mock_news_provider.py -- every article is
 * explicitly fabricated demo content, never a real news report.
 */

export interface NewsEvent {
  headline: string;
  source: string;
  publication_date: string;
  url: string | null;
  relevance_score: number;
  data_source: string;
}

/** One real NASA EONET natural event matched to a route's price
 *  movement -- contextual only, never a claimed cause. See
 *  docs/eonet_context.md. */
export interface NaturalEvent {
  event_id: string;
  title: string;
  category: string;
  category_label: string;
  category_emoji: string;
  event_date: string;
  distance_from_origin_km: number | null;
  distance_from_destination_km: number | null;
  temporal_distance_days: number;
  relevance_score: number;
  relevance_reason: string[];
  source_url: string | null;
  is_closed: boolean;
}

/** Current conditions at one airport (OpenWeatherMap) -- a live
 *  snapshot, not scored/ranked. */
export interface WeatherConditions {
  iata_code: string;
  city_name: string;
  observed_at: string;
  temperature_c: number;
  feels_like_c: number;
  condition: string;
  description: string;
  wind_speed_ms: number;
  humidity_pct: number;
  visibility_m: number | null;
}

export interface RouteContext {
  route: string;
  significant_movement: boolean;
  movement_direction: "up" | "down" | null;
  movement_pct: number | null;
  events: NewsEvent[];
  data_source: string;
  natural_events: NaturalEvent[];
  natural_events_status: "OK" | "UNAVAILABLE";
  weather_origin: WeatherConditions | null;
  weather_destination: WeatherConditions | null;
  weather_status: "OK" | "PARTIAL" | "UNAVAILABLE";
}

/** GET /api/v1/analytics/events -- compact national list, see
 *  api/services/analytics_service.get_natural_events. */
export interface NationalNaturalEvent {
  event_id: string;
  title: string;
  category: string;
  category_label: string;
  category_emoji: string;
  event_date: string;
  route: string;
  route_mom_pct: number;
  relevance_score: number;
  source_url: string | null;
}

export interface NationalNaturalEventsResult {
  events: NationalNaturalEvent[];
  routes_with_significant_movement_checked: number;
  status: "OK" | "UNAVAILABLE";
  data_source: string;
}
