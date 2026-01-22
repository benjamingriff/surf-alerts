"use client";

import { useState } from "react";
import { useAlerts } from "@/lib/alerts-context";
import { Alert } from "@/lib/mock-data";
import { AlertCard } from "@/components/alerts/alert-card";
import { Button } from "@/components/ui/button";

export default function AlertsPage() {
  const { alerts } = useAlerts();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAlert, setEditingAlert] = useState<Alert | null>(null);

  const handleAddNew = () => {
    setEditingAlert(null);
    setIsModalOpen(true);
  };

  const handleEdit = (alert: Alert) => {
    setEditingAlert(alert);
    setIsModalOpen(true);
  };

  const handleDelete = (alert: Alert) => {
    // TODO: Implement delete confirmation dialog (US-020)
    console.log("Delete alert:", alert.id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">My Alerts</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your surf condition alerts
          </p>
        </div>
        <Button onClick={handleAddNew}>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="mr-2 h-4 w-4"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 4.5v15m7.5-7.5h-15"
            />
          </svg>
          Add New Alert
        </Button>
      </div>

      {/* Alerts Grid or Empty State */}
      {alerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            className="mb-4 h-12 w-12 text-muted-foreground"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
            />
          </svg>
          <h3 className="text-lg font-semibold">No alerts yet</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first alert to get notified about surf conditions.
          </p>
          <Button onClick={handleAddNew} className="mt-4">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="mr-2 h-4 w-4"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 4.5v15m7.5-7.5h-15"
              />
            </svg>
            Create Your First Alert
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {alerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* TODO: Add AlertFormModal component (US-015) */}
    </div>
  );
}
