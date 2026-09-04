import { createClient } from "@supabase/supabase-js";

/**
 * Only used for Auth (Google sign-in) -- the dashboard's actual data comes
 * from the backend API (see ../data/client.ts), never queried through this
 * client directly. Both values are safe to expose in frontend code: the
 * publishable/anon key is meant to be public, and every request it makes
 * is subject to the project's own Row Level Security policies.
 */
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isAuthConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

/**
 * `null` when the env vars aren't set (e.g. a contributor's local .env
 * without Supabase configured) -- callers must check isAuthConfigured
 * before using this, same pattern as the rest of the app's "don't crash on
 * missing config" approach.
 */
export const supabase = isAuthConfigured
  ? createClient(SUPABASE_URL as string, SUPABASE_ANON_KEY as string)
  : null;
