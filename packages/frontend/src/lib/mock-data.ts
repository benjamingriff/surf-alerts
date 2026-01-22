// TypeScript types for Surf Alerts

export interface Spot {
  id: string;
  name: string;
  region: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  phone: string;
}

export interface Alert {
  id: string;
  spotId: string;
  spotName: string;
  minRating: number; // 1-5 stars
  days: string[]; // e.g., ['Mon', 'Tue', 'Wed']
  isActive: boolean;
}

// California surf spots data
export const surfSpots: Spot[] = [
  { id: "mavericks", name: "Mavericks", region: "Northern California" },
  { id: "ocean-beach-sf", name: "Ocean Beach SF", region: "Northern California" },
  { id: "steamer-lane", name: "Steamer Lane", region: "Santa Cruz" },
  { id: "pleasure-point", name: "Pleasure Point", region: "Santa Cruz" },
  { id: "the-hook", name: "The Hook", region: "Santa Cruz" },
  { id: "rincon", name: "Rincon", region: "Santa Barbara" },
  { id: "el-capitan", name: "El Capitan", region: "Santa Barbara" },
  { id: "malibu", name: "Malibu", region: "Los Angeles" },
  { id: "venice-breakwater", name: "Venice Breakwater", region: "Los Angeles" },
  { id: "el-porto", name: "El Porto", region: "Los Angeles" },
  { id: "huntington-beach", name: "Huntington Beach", region: "Orange County" },
  { id: "lower-trestles", name: "Lower Trestles", region: "Orange County" },
  { id: "upper-trestles", name: "Upper Trestles", region: "Orange County" },
  { id: "san-onofre", name: "San Onofre", region: "Orange County" },
  { id: "blacks-beach", name: "Blacks Beach", region: "San Diego" },
  { id: "scripps-pier", name: "Scripps Pier", region: "San Diego" },
  { id: "windansea", name: "Windansea", region: "San Diego" },
];

// Mock user data
export const mockUser: User = {
  id: "user-1",
  name: "Alex Rivera",
  email: "alex@example.com",
  phone: "+1 (555) 123-4567",
};

// Mock alerts data
export const mockAlerts: Alert[] = [
  {
    id: "alert-1",
    spotId: "lower-trestles",
    spotName: "Lower Trestles",
    minRating: 4,
    days: ["Sat", "Sun"],
    isActive: true,
  },
  {
    id: "alert-2",
    spotId: "huntington-beach",
    spotName: "Huntington Beach",
    minRating: 3,
    days: ["Mon", "Tue", "Wed", "Thu", "Fri"],
    isActive: true,
  },
  {
    id: "alert-3",
    spotId: "malibu",
    spotName: "Malibu",
    minRating: 5,
    days: ["Sat", "Sun"],
    isActive: false,
  },
];
