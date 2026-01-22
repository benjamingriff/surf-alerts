"use client";

import { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth-context";
import { AlertsProvider } from "@/lib/alerts-context";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AlertsProvider>{children}</AlertsProvider>
    </AuthProvider>
  );
}
