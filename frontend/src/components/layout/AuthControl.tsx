import { useAuth, signInWithGoogle, signOut } from "../../hooks/useAuth";
import { isAuthConfigured } from "../../lib/supabaseClient";

/** Renders nothing if Supabase Auth isn't configured (no VITE_SUPABASE_URL/
 *  VITE_SUPABASE_ANON_KEY) -- signing in is optional, the dashboard itself
 *  has no per-user data or gated views. */
export function AuthControl() {
  const { session, loading } = useAuth();

  if (!isAuthConfigured || loading) return null;

  if (!session) {
    return (
      <button
        type="button"
        onClick={signInWithGoogle}
        className="inline-flex items-center gap-2 rounded-full border border-hairline-strong bg-surface px-3 py-1.5 text-[0.72rem] font-medium text-ink-muted transition-colors hover:bg-surface-sunken"
      >
        <GoogleMark />
        Sign in with Google
      </button>
    );
  }

  const user = session.user;
  const name = (user.user_metadata?.full_name as string | undefined) ?? user.email ?? "Signed in";
  const avatarUrl = user.user_metadata?.avatar_url as string | undefined;

  return (
    <div className="flex items-center gap-2">
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="h-6 w-6 rounded-full" referrerPolicy="no-referrer" />
      ) : (
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-sunken text-[0.62rem] font-semibold text-ink-muted">
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="hidden max-w-[9rem] truncate text-[0.72rem] text-ink-muted sm:inline">{name}</span>
      <button
        type="button"
        onClick={signOut}
        className="rounded-full border border-hairline-strong bg-surface px-2.5 py-1 text-[0.68rem] font-medium text-ink-faint transition-colors hover:bg-surface-sunken hover:text-ink-muted"
      >
        Sign out
      </button>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg width="14" height="14" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.1 8 3l6-6C34 5.1 29.3 3 24 3 12.4 3 3 12.4 3 24s9.4 21 21 21 21-9.4 21-21c0-1.4-.1-2.7-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 15.9 18.9 13 24 13c3.1 0 5.8 1.1 8 3l6-6C34 5.1 29.3 3 24 3 16.3 3 9.7 7.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 45c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 36.2 26.7 37 24 37c-5.3 0-9.6-3.4-11.3-8l-6.5 5C9.6 40.6 16.2 45 24 45z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.2 4.2-4.1 5.6l6.2 5.2C40.9 36.3 44 30.8 44 24c0-1.4-.1-2.7-.4-3.5z"
      />
    </svg>
  );
}
