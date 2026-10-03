import type { ReactNode } from "react";

export default function ClientLayout({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <header className="topbar">
        <strong>EquiContracts · Verified client view</strong>
        <span>Read only</span>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
