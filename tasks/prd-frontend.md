# PRD: Surf Alerts Frontend

## 1. Introduction/Overview

Surf Alerts needs a frontend web application to allow users to interact with the surf alert system. The frontend will provide a public-facing landing page to describe and market the product, and a private dashboard where authenticated users can configure their mobile phone for text alerts and set up personalized surf condition notifications.

**Problem it solves:** Currently, there is no user interface for the surf alerts system. Users need a way to discover the product, sign up, and configure their alert preferences without technical knowledge.

**Note:** This PRD focuses on UI/UX design and layout. Authentication will be stubbed/mocked for initial development to allow rapid iteration on the user experience.

## 2. Goals

1. Create a visually appealing landing page that clearly communicates the value proposition of Surf Alerts
2. Build a functional dashboard UI where users can manage their phone number and alert configurations
3. Enable users to create multiple surf alerts with different spot/rating/day combinations
4. Establish a modern, minimalist design system that can scale as features are added
5. Validate the UX flow before implementing backend integrations

## 3. User Stories

### Landing Page
- **As a visitor**, I want to understand what Surf Alerts does within seconds of landing on the page, so I can decide if it's relevant to me.
- **As a visitor**, I want to see how the alerting system works, so I can understand the value before signing up.
- **As a visitor**, I want to easily find a way to sign up or log in, so I can start using the service.

### Authentication (Mocked for MVP)
- **As a visitor**, I want to click a login/signup button and be taken to a login page, so I can access my dashboard.
- **As a user**, I want the login flow to feel professional and trustworthy, even if it's mocked for now.

### Dashboard - Phone Setup
- **As a logged-in user**, I want to add my mobile phone number, so I can receive text alerts.
- **As a user**, I want to see confirmation that my phone number is saved, so I know alerts will reach me.

### Dashboard - Alert Configuration
- **As a user**, I want to create a new surf alert by selecting a surf spot from a list, so I can monitor conditions at my favorite breaks.
- **As a user**, I want to set a minimum rating (1-5 stars) for each alert, so I only get notified when conditions meet my standards.
- **As a user**, I want to select which days of the week I'm likely to surf, so alerts are relevant to my schedule.
- **As a user**, I want to create multiple alerts with different configurations, so I can monitor several spots with different thresholds.
- **As a user**, I want to view, edit, and delete my existing alerts, so I can manage my preferences over time.

## 4. Functional Requirements

### 4.1 Landing Page

1. The landing page must display a hero section with a clear headline, subheadline, and call-to-action button
2. The page must include a "How it Works" section explaining the alert flow (pick spots → set threshold → get texts)
3. The page must include a features/benefits section highlighting key value propositions
4. The page must have a visible navigation with Login/Sign Up buttons
5. The page must be fully responsive (mobile, tablet, desktop)
6. The page must follow a modern minimalist design aesthetic (clean lines, whitespace, subtle colors)

### 4.2 Authentication Pages (UI Only)

7. The system must display a login page with email/password fields and a submit button
8. The system must display a signup page with email/password/confirm password fields
9. For MVP, clicking login/signup should navigate directly to the dashboard (no actual auth)
10. The UI should be designed to easily integrate with BetterAuth or WorkOS in the future

### 4.3 Dashboard - Overview

11. The dashboard must have a fixed sidebar navigation for navigating between sections
12. The dashboard must display a welcome message with the user's name (mocked)
13. The dashboard must show a summary of active alerts count

### 4.4 Dashboard - Phone Setup

14. The system must provide a form to enter/update the user's mobile phone number
15. The system must display the currently saved phone number (if any)
16. The system must show a success state when the phone number is "saved" (mocked)
17. Phone number input should include basic format validation (UI-level)

### 4.5 Dashboard - Alert Management

18. The system must display a list/grid of all configured alerts
19. Each alert card must show: surf spot name, minimum rating, selected days
20. The system must provide an "Add New Alert" button that opens a creation form/modal
21. The alert creation form must include:
    - A dropdown/select to choose from a predefined list of surf spots
    - A rating selector (1-5 stars) for minimum alert threshold
    - Day-of-week checkboxes (Mon-Sun) for when the user surfs
    - A live preview showing what the text message will look like
22. The system must allow users to edit existing alerts
23. The system must allow users to delete alerts with a confirmation step
24. The system must support creating multiple alerts (no limit for MVP)

### 4.6 Surf Spots Data

25. The system must include a predefined list of real Surfline surf spots that match the existing scraper data
26. Each spot should display its name and its location/region
27. Spot data should use actual Surfline spot names/IDs for consistency with the backend scrapers

## 5. Non-Goals (Out of Scope)

- **Actual authentication** - Login/signup will be UI-only; no real auth integration for MVP
- **Backend integration** - No API calls to save data; all state will be local/mocked
- **Real text message sending** - No SMS integration
- **User account management** - No profile editing, password reset, etc.
- **Payment/subscription** - No billing or premium tiers
- **Real-time surf data display** - Dashboard won't show current conditions
- **Mobile native app** - Web only for MVP
- **Email notifications** - Text alerts only in the design
- **First-time user onboarding** - Planned for future iteration, not in MVP

## 6. Design Considerations

### Branding
- **Logo/Name:** Placeholder branding to be created (can be swapped for final branding later)
- **Brand Name:** "Surf Alerts" (working title, can be changed)

### Visual Style
- **Aesthetic:** Modern minimalist - clean lines, generous whitespace, subtle color palette
- **Primary colors:** Ocean-inspired blues and teals as accents, with neutral grays/whites as base
- **Typography:** Clean sans-serif font (e.g., Inter, SF Pro, or similar)
- **Components:** Rounded corners, subtle shadows, smooth transitions

### UI Components to Consider
- Tailwind CSS or similar utility-first framework for rapid styling
- shadcn/ui or Radix UI for accessible, unstyled component primitives
- Framer Motion for subtle animations (optional)

### Key Screens
1. Landing Page (/)
2. Login Page (/login)
3. Signup Page (/signup)
4. Dashboard Home (/dashboard)
5. Alert Configuration (/dashboard/alerts or modal)
6. Phone Setup (/dashboard/settings or inline in dashboard)

## 7. Technical Considerations

### Technology Stack
- **Framework:** Next.js 14+ (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (recommended for consistency and accessibility)
- **State Management:** React useState/useContext for MVP (no need for complex state)
- **Deployment:** Vercel (pairs well with Next.js)

### Project Structure Suggestion
```
packages/frontend/
├── src/
│   ├── app/
│   │   ├── page.tsx              # Landing page
│   │   ├── login/page.tsx        # Login page
│   │   ├── signup/page.tsx       # Signup page
│   │   └── dashboard/
│   │       ├── page.tsx          # Dashboard home
│   │       └── layout.tsx        # Dashboard layout with nav
│   ├── components/
│   │   ├── ui/                   # shadcn components
│   │   ├── landing/              # Landing page sections
│   │   ├── dashboard/            # Dashboard components
│   │   └── alerts/               # Alert-related components
│   ├── lib/
│   │   └── mock-data.ts          # Predefined surf spots, mock user data
│   └── styles/
│       └── globals.css
├── package.json
├── tailwind.config.ts
└── next.config.js
```

### Auth Integration Notes (Future)
- Design auth pages to be compatible with BetterAuth or WorkOS
- Use a simple auth context that can be swapped for real auth later
- Consider NextAuth.js as another option for easy provider integration

## 8. Success Metrics

Since this is a UI/UX focused MVP, success will be measured by:

1. **Design Approval:** Stakeholder sign-off on the visual design and user flow
2. **Usability:** A new user can complete the full flow (landing → "login" → add phone → create alert) without confusion
3. **Responsiveness:** All pages render correctly on mobile (375px), tablet (768px), and desktop (1280px+)
4. **Code Quality:** Clean, maintainable component structure ready for backend integration
5. **Performance:** Landing page achieves 90+ Lighthouse performance score

## 9. Resolved Decisions

- **Surf Spots:** Use real Surfline spot names/IDs that match existing scraper data
- **Branding:** Create placeholder branding (logo, colors) that can be swapped later
- **Dashboard Layout:** Fixed sidebar navigation
- **Alert Preview:** Yes, show a preview of what the text message will look like when creating/editing an alert
- **Onboarding:** Plan for first-time user onboarding flow in future iterations, but leave out of MVP

---

*Generated following the PRD template from ralph/create-prd.md*
