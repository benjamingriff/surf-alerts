import Link from "next/link";
import { Header } from "@/components/landing/header";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        {/* Hero Section */}
        <section className="relative overflow-hidden">
          {/* Ocean-themed background */}
          <div className="absolute inset-0 -z-10">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-accent/5 to-background" />
            <div className="absolute top-0 left-1/4 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
            <div className="absolute bottom-0 right-1/4 h-96 w-96 rounded-full bg-accent/10 blur-3xl" />
            {/* Wave pattern placeholder */}
            <svg
              className="absolute bottom-0 left-0 right-0 h-24 w-full text-background opacity-50 sm:h-32 md:h-40"
              viewBox="0 0 1440 320"
              preserveAspectRatio="none"
            >
              <path
                fill="currentColor"
                d="M0,160L48,170.7C96,181,192,203,288,192C384,181,480,139,576,133.3C672,128,768,160,864,181.3C960,203,1056,213,1152,197.3C1248,181,1344,139,1392,117.3L1440,96L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
              />
            </svg>
          </div>

          <div className="container mx-auto max-w-7xl px-4 py-24 sm:px-6 sm:py-32 lg:px-8 lg:py-40">
            <div className="mx-auto max-w-3xl text-center">
              {/* Headline */}
              <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl md:text-6xl">
                Never Miss the{" "}
                <span className="text-primary">Perfect Wave</span>
              </h1>

              {/* Subheadline */}
              <p className="mt-6 text-lg leading-8 text-muted-foreground sm:text-xl">
                Get instant text alerts when your favorite surf spots hit your
                ideal conditions. Set your rating threshold, pick your days, and
                we&apos;ll let you know when it&apos;s time to paddle out.
              </p>

              {/* CTA Button */}
              <div className="mt-10 flex items-center justify-center gap-4">
                <Button asChild size="lg" className="text-base px-8 py-6">
                  <Link href="/signup">Get Started</Link>
                </Button>
                <Button asChild variant="outline" size="lg" className="text-base px-8 py-6">
                  <Link href="#how-it-works">Learn More</Link>
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
