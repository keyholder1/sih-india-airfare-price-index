import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabaseClient";

interface AuthState {
  session: Session | null;
  loading: boolean;
}

/** Tracks the current Supabase Auth session -- `session` stays `null` and
 *  `loading` resolves to `false` immediately if Supabase Auth isn't
 *  configured (see supabaseClient.ts), so the dashboard works the same
 *  with or without auth wired up. */
export function useAuth(): AuthState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(supabase));

  useEffect(() => {
    if (!supabase) return;

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    return () => subscription.subscription.unsubscribe();
  }, []);

  return { session, loading };
}

export function signInWithGoogle(): void {
  if (!supabase) return;
  supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin },
  });
}

export function signOut(): void {
  if (!supabase) return;
  supabase.auth.signOut();
}
