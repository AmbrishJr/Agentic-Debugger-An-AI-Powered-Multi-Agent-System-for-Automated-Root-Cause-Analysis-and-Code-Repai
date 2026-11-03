"use client";
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Detail } from "@/types";
export function useIncident(id: string) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["incident", id],
    queryFn: () => api<Detail>(`/incidents/${id}`),
    refetchInterval: (q) =>
      q.state.data?.status === "investigating" ? 2500 : false,
  });
  useEffect(() => {
    if (query.data?.status !== "investigating") return;
    const stream = new EventSource(`/api/incidents/${id}/events`);
    const refresh = () => {
      void client.invalidateQueries({ queryKey: ["incident", id] });
    };
    stream.addEventListener("progress", refresh);
    stream.addEventListener("complete", () => {
      refresh();
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      stream.close();
    });
    return () => stream.close();
  }, [id, query.data?.status, client]);
  return query;
}
