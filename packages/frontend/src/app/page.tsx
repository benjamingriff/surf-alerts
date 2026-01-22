import { Header } from "@/components/landing/header";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h1 className="text-3xl font-bold text-foreground">
          Welcome to Surf Alerts
        </h1>
        <p className="mt-4 text-muted-foreground">
          Landing page content coming soon...
        </p>
      </main>
    </div>
  );
}
