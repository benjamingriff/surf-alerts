"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function SettingsPage() {
  const { user, updatePhone } = useAuth();
  const [phone, setPhone] = useState(user?.phone || "");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  // Basic US phone format validation
  const validatePhone = (value: string): boolean => {
    // Accept formats like: +1 (555) 123-4567, 555-123-4567, 5551234567, etc.
    const phoneRegex = /^[\d\s\-\(\)\+]+$/;
    const digitsOnly = value.replace(/\D/g, "");

    if (!value.trim()) {
      setError("Phone number is required");
      return false;
    }

    if (!phoneRegex.test(value)) {
      setError("Please enter a valid phone number");
      return false;
    }

    if (digitsOnly.length < 10 || digitsOnly.length > 15) {
      setError("Phone number must be between 10 and 15 digits");
      return false;
    }

    setError("");
    return true;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess(false);

    if (validatePhone(phone)) {
      updatePhone(phone);
      setSuccess(true);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="mt-1 text-muted-foreground">
          Manage your account settings and preferences.
        </p>
      </div>

      {/* Phone Settings Card */}
      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="h-5 w-5"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10.5 1.5H8.25A2.25 2.25 0 0 0 6 3.75v16.5a2.25 2.25 0 0 0 2.25 2.25h7.5A2.25 2.25 0 0 0 18 20.25V3.75a2.25 2.25 0 0 0-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3"
              />
            </svg>
            Phone Number
          </CardTitle>
          <CardDescription>
            Add your mobile phone number to receive surf alert text messages.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {/* Current Phone Display */}
            {user?.phone && (
              <div className="rounded-lg border bg-muted/30 p-3">
                <p className="text-sm text-muted-foreground">Current number</p>
                <p className="font-medium">{user.phone}</p>
              </div>
            )}

            {/* Phone Input */}
            <div className="space-y-2">
              <Label htmlFor="phone">Phone Number</Label>
              <Input
                id="phone"
                type="tel"
                placeholder="+1 (555) 123-4567"
                value={phone}
                onChange={(e) => {
                  setPhone(e.target.value);
                  setSuccess(false);
                  if (error) setError("");
                }}
                aria-invalid={!!error}
              />
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
            </div>

            {/* Success Message */}
            {success && (
              <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-5 w-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                  />
                </svg>
                <span className="text-sm font-medium">
                  Phone number saved successfully!
                </span>
              </div>
            )}

            {/* Save Button */}
            <Button type="submit" className="w-full sm:w-auto">
              Save Phone Number
            </Button>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}
