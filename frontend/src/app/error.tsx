"use client";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div className="empty-state">
      <h1>Something went wrong.</h1>
      <p>
        Try loading this page again. Persisted investigations are kept on the
        backend.
      </p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
