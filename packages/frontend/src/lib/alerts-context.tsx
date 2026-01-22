"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { Alert, mockAlerts } from "./mock-data";

const STORAGE_KEY = "surf-alerts-data";

interface AlertsContextType {
  alerts: Alert[];
  addAlert: (alert: Omit<Alert, "id">) => void;
  updateAlert: (id: string, alert: Partial<Alert>) => void;
  deleteAlert: (id: string) => void;
}

const AlertsContext = createContext<AlertsContextType | undefined>(undefined);

function getInitialAlerts(): Alert[] {
  if (typeof window === "undefined") {
    return mockAlerts;
  }

  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      return mockAlerts;
    }
  }

  // First time: seed localStorage with mock data
  localStorage.setItem(STORAGE_KEY, JSON.stringify(mockAlerts));
  return mockAlerts;
}

export function AlertsProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<Alert[]>(getInitialAlerts);

  const persistAlerts = (newAlerts: Alert[]) => {
    setAlerts(newAlerts);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newAlerts));
    }
  };

  const addAlert = (alertData: Omit<Alert, "id">) => {
    const newAlert: Alert = {
      ...alertData,
      id: `alert-${Date.now()}`,
    };
    persistAlerts([...alerts, newAlert]);
  };

  const updateAlert = (id: string, updates: Partial<Alert>) => {
    const newAlerts = alerts.map((alert) =>
      alert.id === id ? { ...alert, ...updates } : alert
    );
    persistAlerts(newAlerts);
  };

  const deleteAlert = (id: string) => {
    const newAlerts = alerts.filter((alert) => alert.id !== id);
    persistAlerts(newAlerts);
  };

  const value: AlertsContextType = {
    alerts,
    addAlert,
    updateAlert,
    deleteAlert,
  };

  return (
    <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
  );
}

export function useAlerts() {
  const context = useContext(AlertsContext);
  if (context === undefined) {
    throw new Error("useAlerts must be used within an AlertsProvider");
  }
  return context;
}
