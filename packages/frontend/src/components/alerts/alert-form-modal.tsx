"use client";

import { useState, useEffect } from "react";
import { Alert, Spot, surfSpots } from "@/lib/mock-data";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

const ALL_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
type DayOfWeek = (typeof ALL_DAYS)[number];

interface AlertFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingAlert?: Alert | null;
}

// Group spots by region
function getSpotsByRegion(): Map<string, Spot[]> {
  const grouped = new Map<string, Spot[]>();
  for (const spot of surfSpots) {
    const spots = grouped.get(spot.region) || [];
    spots.push(spot);
    grouped.set(spot.region, spots);
  }
  return grouped;
}

function DaySelector({
  selectedDays,
  onChange,
}: {
  selectedDays: string[];
  onChange: (days: string[]) => void;
}) {
  const toggleDay = (day: DayOfWeek) => {
    if (selectedDays.includes(day)) {
      onChange(selectedDays.filter((d) => d !== day));
    } else {
      onChange([...selectedDays, day]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Select days">
      {ALL_DAYS.map((day) => {
        const isSelected = selectedDays.includes(day);
        return (
          <button
            key={day}
            type="button"
            role="checkbox"
            aria-checked={isSelected}
            onClick={() => toggleDay(day)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              isSelected
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {day}
          </button>
        );
      })}
    </div>
  );
}

function StarRatingSelector({
  rating,
  onChange,
}: {
  rating: number;
  onChange: (rating: number) => void;
}) {
  const [hoverRating, setHoverRating] = useState(0);

  return (
    <div
      className="flex gap-1"
      onMouseLeave={() => setHoverRating(0)}
      role="radiogroup"
      aria-label="Select minimum rating"
    >
      {[1, 2, 3, 4, 5].map((star) => {
        const isActive = star <= (hoverRating || rating);
        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={star === rating}
            aria-label={`${star} star${star > 1 ? "s" : ""}`}
            className="rounded p-1 transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => onChange(star)}
            onMouseEnter={() => setHoverRating(star)}
          >
            <svg
              className={`h-6 w-6 transition-colors ${
                isActive
                  ? "fill-amber-400 text-amber-400"
                  : "fill-transparent text-muted-foreground/40"
              }`}
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </button>
        );
      })}
    </div>
  );
}

export function AlertFormModal({
  open,
  onOpenChange,
  editingAlert,
}: AlertFormModalProps) {
  const [selectedSpotId, setSelectedSpotId] = useState("");
  const [minRating, setMinRating] = useState(0);
  const [selectedDays, setSelectedDays] = useState<string[]>([]);

  const spotsByRegion = getSpotsByRegion();
  const selectedSpot = surfSpots.find((s) => s.id === selectedSpotId);

  // Reset form when modal opens/closes or when editing alert changes
  useEffect(() => {
    if (open) {
      if (editingAlert) {
        setSelectedSpotId(editingAlert.spotId);
        setMinRating(editingAlert.minRating);
        setSelectedDays(editingAlert.days);
      } else {
        setSelectedSpotId("");
        setMinRating(0);
        setSelectedDays([]);
      }
    }
  }, [open, editingAlert]);

  const isEditing = !!editingAlert;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Edit Alert" : "Create New Alert"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update your alert settings below."
              : "Configure your surf alert to get notified when conditions are good."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Spot Selection */}
          <div className="space-y-2">
            <Label htmlFor="spot-select">Surf Spot</Label>
            <Select value={selectedSpotId} onValueChange={setSelectedSpotId}>
              <SelectTrigger id="spot-select" className="w-full">
                <SelectValue placeholder="Select a surf spot" />
              </SelectTrigger>
              <SelectContent>
                {Array.from(spotsByRegion.entries()).map(([region, spots]) => (
                  <SelectGroup key={region}>
                    <SelectLabel>{region}</SelectLabel>
                    {spots.map((spot) => (
                      <SelectItem key={spot.id} value={spot.id}>
                        {spot.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            {selectedSpot && (
              <p className="text-xs text-muted-foreground">
                Region: {selectedSpot.region}
              </p>
            )}
          </div>

          {/* Rating Selection */}
          <div className="space-y-2">
            <Label>Minimum Rating</Label>
            <StarRatingSelector rating={minRating} onChange={setMinRating} />
            {minRating > 0 && (
              <p className="text-xs text-muted-foreground">
                Alert when conditions are {minRating}+ stars
              </p>
            )}
          </div>

          {/* Day Selection */}
          <div className="space-y-2">
            <Label>Alert Days</Label>
            <DaySelector
              selectedDays={selectedDays}
              onChange={setSelectedDays}
            />
            {selectedDays.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Select at least one day to receive alerts
              </p>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
