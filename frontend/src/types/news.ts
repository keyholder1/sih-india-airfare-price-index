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

export interface RouteContext {
  route: string;
  significant_movement: boolean;
  movement_direction: "up" | "down" | null;
  movement_pct: number | null;
  events: NewsEvent[];
  data_source: string;
}
