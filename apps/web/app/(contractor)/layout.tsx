import Link from "next/link";
import type { ReactNode } from "react";

export default function ContractorLayout({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <header className="topbar">
        <strong>EquiContracts · Contractor</strong>
        <nav aria-label="Contractor navigation">
          <Link href="/setup">Setup</Link>
          <Link href="/review">Inbox Review</Link>
        </nav>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
