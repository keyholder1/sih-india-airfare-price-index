export * from "./analytics";
export * from "./routes";
export * from "./dataQuality";
export * from "./forecast";

/**
 * Provenance of the airfare observations currently behind the numbers.
 * Until the scraper/backend is wired in, airfare data is SYNTHETIC and the
 * UI must say so. DGCA traffic / route metadata / coordinates are REAL.
 */
export type DataLevel = "LIVE" | "PUBLIC" | "SYNTHETIC";

export interface DataStatus {
  level: DataLevel;
  label: string;
  detail: string;
  /** period the current figures describe, e.g. "2026-08" */
  asOf: string;
}
