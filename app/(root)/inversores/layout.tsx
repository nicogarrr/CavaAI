import { Suspense, type ReactNode } from "react";
import { HubNav } from "./_components/HubNav";

export default function InvestorsLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <HubNav />
      </Suspense>
      {children}
    </>
  );
}
