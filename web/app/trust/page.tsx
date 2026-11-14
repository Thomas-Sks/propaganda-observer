import { Suspense } from "react";
import TrustCard from "@/components/trust/TrustCard";

export const metadata = { title: "Trust card · Propaganda Observer" };

export default function TrustPage({ searchParams }: PageProps<"/trust">) {
  return (
    <Suspense fallback={<div className="grid-bg min-h-screen" />}>
      <Trust searchParams={searchParams} />
    </Suspense>
  );
}

async function Trust({ searchParams }: { searchParams: PageProps<"/trust">["searchParams"] }) {
  const t = (await searchParams).target;
  return <TrustCard initial={typeof t === "string" ? t : ""} />;
}
