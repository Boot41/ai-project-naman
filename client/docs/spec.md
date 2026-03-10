# OpsCopilot Frontend Feature Spec

## 1. Objective
Build a production-quality, reusable, desktop-first OpsCopilot investigation UI (mobile-friendly) with login-first access control.

- First screen: Login page
- After successful login: Chat/investigation page
- No backend dependency for this phase
- Frontend-only auth gate for test credentials:
  - Email: `user1@example.com`
  - Password: `123456`

## 2. Scope
### In scope
- Login page UI/UX and client-side validation
- Frontend-only auth/session persistence using local storage
- Dark-themed OpsCopilot chat shell matching current product direction
- Reusable UI components for sidebar, header, message area, and composer
- Placeholder API seam comments/hooks for future backend integration
- Accessibility and keyboard behavior
- Responsive behavior with collapsible sidebar on smaller screens

### Out of scope
- Real authentication API
- Real assistant streaming API
- Server-side authorization
- Multi-user backend persistence

## 3. Information Architecture
Routes:
- `/login`: public login page
- `/app`: protected investigation page
- `*`: redirect based on auth state

Guarding rules:
- If unauthenticated and route is `/app`, redirect to `/login`
- If authenticated and route is `/login`, redirect to `/app`

## 4. Visual Design System
Design goals:
- Modern operations console feel
- Clean, text-first, low-clutter layout
- Dark theme aligned with OpsCopilot shell
- Subtle blue accent with clear visual hierarchy

Token direction:
- Background: `#050d24`
- Surface: `#09142f`, secondary surfaces `#101e3b`
- Borders: low-contrast blue slate (`#1d2a45`, `#22355a`)
- Text primary: light blue-white (`#d7e8ff`)
- Text secondary: muted blue (`#7f98c3` / `#8ca7d4`)
- Accent: action blue (`#2160f3`)

Typography:
- Primary UI font: `Manrope` (fallback sans-serif)

## 5. Component Architecture
Reusable components:
- `LoginForm`
- `Sidebar`
- `SessionList`
- `SessionItem`
- `ChatHeader`
- `MessageList`
- `MessageBubble`
- `Composer`

Supporting modules:
- `hooks/useAuth.tsx`
- `hooks/useChatState.ts`
- `types/chat.ts`

## 6. Functional Requirements
### 6.1 Login page
- Centered card layout in dark theme
- Product title + short description
- Inputs: email + password
- Validation:
  - Required fields
  - Valid email format
  - Invalid credentials error state
- Submit button disabled while submitting/invalid
- Keyboard submit support
- On success:
  - Save auth state in local storage
  - Navigate to `/app`

### 6.2 Chat app shell
- Left fixed/collapsible sidebar
- Main area with:
  - Top header
  - Scrollable message area
  - Bottom composer

### 6.3 Sidebar
Contains only:
- OpsCopilot logo/title
- `New Investigation` button
- Search investigations input
- `Recent Investigations` list

Session item fields:
- Short title
- Last updated text
- Active/selected state

### 6.4 Top header
- Logout action on the left side
- Active incident title and subtitle in center/primary region
- Right-side actions:
  - `Export JSON`
  - `Resolve Incident`

### 6.5 Conversation states
- Starts with an empty canvas state (no seeded mock conversation)
- User messages render as right-aligned blue bubbles
- Placeholder assistant integration remains for future backend wiring

### 6.6 Composer
- Multiline auto-grow textarea
- Attach button placeholder
- Voice button placeholder
- Send button
- Keyboard behavior:
  - Enter = send
  - Shift+Enter = newline
- Disabled send state when request is pending

## 7. Data and State Model
Auth state:
- `isAuthenticated`, `userEmail`
- persisted in local storage

Chat state:
- `selectedSessionId`
- `searchQuery`
- `draft`
- `isSending`
- in-memory session/message state for UI behavior only

### Placeholder API seams
- `TODO` comments indicate where login/chat APIs will be connected later

## 8. Accessibility Requirements
- Semantic structure (`main`, `header`, `aside`, form labels)
- Keyboard navigable interactive elements
- Visible focus states
- ARIA labels for icon-only actions
- Proper disabled semantics for controls

## 9. Responsive Behavior
Desktop-first breakpoints:
- `>=1024px`: persistent sidebar
- `<1024px`: drawer sidebar with menu trigger

Behavior:
- Long conversation scroll within content area
- Composer remains accessible on mobile
- Session switching remains simple on mobile drawer

## 10. Acceptance Criteria
- Login is required to access `/app`
- Frontend test credentials gate access
- Sidebar contains only investigation controls (no Data Sources/Settings/Logout)
- Logout is available in top header
- Top header actions remain `Export JSON` and `Resolve Incident`
- Empty-state-first conversation experience is present
- App remains responsive and keyboard-usable
- Build runs without backend integration
