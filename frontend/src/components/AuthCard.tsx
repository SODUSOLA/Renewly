import type { ReactNode } from "react";

// The centred card shared by the sign-in, sign-up and password-reset pages.
export function AuthCard({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <img src="/favicon.svg" alt="" width="34" height="34" />
          <span>Renewly</span>
        </div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
        {children}
      </div>
    </main>
  );
}
