# Practical Guidelines for Circadian Lighting Programs with implmentation logic


A field guide to setting up automatic, circadian-aware lighting in homes and workplaces.

---

## 1. What the Biology Actually Cares About

The key biological metric is **circadian-effective light at the eye**, often expressed as *melanopic equivalent daylight illuminance* (melanopic EDI / EML).

Consensus from recent research and standards bodies (CIE, WELL, Brown et al. 2022, etc.) is roughly:

- **Daytime (wake hours):**
  - Aim for **≥ 250 melanopic lux at the eye** for several hours.
- **Evening (~3 hours before habitual bedtime):**
  - Keep **melanopic EDI ≤ 10 lux** at the eye.
- **Night (during sleep):**
  - Ideally **≤ 1 melanopic lux**  
  - If light is needed for safety, **keep melanopic as low as possible** (≤ 10 lux at the eye).

**Big picture:**  
You want **bright, circadian-effective light in the daytime** and **very low, warm, circadian-ineffective light in the evening and night**. CCT and brightness are just control knobs to achieve that at eye level.

---

## 2. A Simple Time-of-Day Circadian Schedule

Think “slow, predictable daily rhythm” rather than reacting to every passing cloud.

### Example Daily Program (for a typical day-active adult)

| Phase                         | Approx. Time         | Goal                                      | Typical Target                                                |
|------------------------------|----------------------|-------------------------------------------|----------------------------------------------------------------|
| Pre-wake / very early        | 1–2 h before wake    | Avoid strong phase-shifting               | Very dim, warm (≤ 2700K, < 20 lux at eye)                     |
| Morning ramp                 | Wake–~10:00          | Strong “daytime” signal, alertness        | 350–600 lux at eye, 4000–6500K, melanopic ≥ 250              |
| Midday plateau               | ~10:00–15:00         | Maintain strong daytime cue               | 500–1000 lux at eye, 4000–6500K, melanopic high; avoid glare |
| Late afternoon               | ~15:00–3h pre-bed    | Ease intensity, still “daylike”           | 300–500 lux at eye, 3500–4500K                               |
| Evening                      | ~3h pre-bed          | Allow melatonin rise, “wind-down”         | Warm (2200–3000K), < 100 lux at eye, melanopic low           |
| Night (sleep)                | Bed–wake             | Stable clock, undisturbed sleep           | Dark; if needed, ≤ 1–5 lux, very warm/amber                  |

**Automation tips:**

- Use **preset curves** for CCT and brightness across the day.
- Make transitions **slow (20–45 minutes)** so they are barely noticeable.
- Allow **local overrides** (wall keypad, app, voice), but gently return to the schedule over time.

---

## 3. Should Indoor Lighting Track Outdoor Brightness / CCT?

### Short Answer

- **Brightness:** Yes, somewhat. Use outdoor/daylight information to:
  - **Dim electric light** when daylight is abundant.
  - **Boost electric light** when daylight is weak (cloudy/winter) to keep daytime circadian targets.
- **CCT:** Mostly no.  
  - Drive **CCT by time-of-day and activity**, not clouds or exact sky color.

### Why This Approach

1. **Daylight is highly variable.**  
   On overcast days, people often fall below recommended circadian-effective light levels unless electric lights compensate.

2. **Chasing every cloud is a bad user experience.**  
   Rapid shifts in brightness or color temperature are distracting and not clearly more “healthy.”

3. **There is no strong evidence that fully mimicking outdoor CCT minute-by-minute provides extra circadian benefits** beyond:
   - Bright, high-melanopic days.
   - Very low-melanopic evenings/nights.

### Practical Control Strategy

For each daytime period:

1. **Define a minimum target** for eye-level light (or a proxy, if you can’t compute melanopic lux).
2. Use a **daylight sensor**:
   - If measured light **already exceeds the target**, dim electric lights (energy + comfort).
   - If it is **below the target**, raise electric lights (within glare/comfort limits).
3. Keep **CCT primarily tied to time-of-day**:
   - Cloudy morning? Still run a “daytime” CCT (e.g. 4000–5000K).
   - Harsh sun? Don’t push indoor CCT to crazy-high values just because the sky is blue.

---

## 4. Seasonal Adjustments

### Should You Adjust for Season?

**Yes, but gently.**  
The *biological* recommendations don’t change by season, but **the daylight available does**:

- Winter: shorter days, lower solar elevation, often overcast → weaker natural stimulus.
- Summer: long days, more intense sun → risk of glare/over-brightness.

### Seasonal Best Practices

- Keep the **same general pattern year-round**:
  - Morning ramp → bright midday → softer late afternoon → warm/dim evening.
- In **winter**:
  - Allow **higher electric brightness** during the day to compensate for weak daylight.
  - Consider **extending the “bright daytime” window** so your “biological day” isn’t too short.
- In **summer**:
  - Use **shades + dimming** to avoid glare while still providing sufficient circadian-effective light.

**Anchor the schedule to local time and occupant routines**, not strictly sunrise/sunset.  
Example: if someone wakes at 6:30 in winter, you still want a morning ramp that starts near then, even if sunrise is much later.

---

## 5. Different Programs for Different Environments

### 5.1. Offices / Workspaces

**Goals:** alertness, performance, consistent conditions.

General guidance for day-active workers:

- **Daytime at the desk:**
  - Vertical illuminance at the eye: **~300–1000 lux** depending on tasks.
  - CCT: **4000–6500K**.
  - Ensure the **melanopic daytime target** (≥ ~200–250 melanopic lux) is met for several hours.
- **Late afternoon:**
  - Gradually reduce intensity.
  - Optionally shift slightly warmer (e.g. toward 3500K).
- **After hours:**
  - Lower intensity and possibly CCT.
  - Avoid strong high-melanopic exposure for workers who are close to bedtime (shift-work is a special case).

Focus for offices:

- Design and measure for **vertical light at face/eye level**, not just horizontal at the desk.
- Use **slow dynamic changes**; avoid fast color/intensity jumps.

---

### 5.2. Homes

Homes have mixed priorities: comfort, aesthetics, sleep, and multiple uses in one room.

**Typical per-room strategies:**

#### a) Kitchen / Home Office / Workshop

- **Daytime:**
  - CCT: **3500–5000K**.
  - Brightness: **300–700 lux** at task plane; good daytime stimulus.
- **Evening:**
  - Let these rooms follow the general house evening program: warmer and dimmer if not being used for intense work.

#### b) Living / Dining / Lounge

- **Day:**
  - CCT: **3000–4000K**, moderate brightness.
  - Encourage daylight usage.
- **Evening (3h pre-bed onward):**
  - Shift to **very warm (2200–2700K)**.
  - Reduce brightness significantly.
  - Prefer **indirect light, wall washing, lamps** instead of bright downlights.

#### c) Bedrooms

- **Day:**
  - Modest brightness; don’t rely on bedrooms as the primary circadian light source if you can avoid it.
- **Evening (3h pre-bed):**
  - **Strongly limit melanopic light.**  
    - Very warm, low brightness, bedside lamps vs. overheads.
- **Night:**
  - Dark if possible.
  - If needed for safety, use **very low-level amber/very warm nightlights** at floor level.

**Home design pattern:**

- Use **different circadian curves per room type**:
  - “Office”, “Kitchen”, “Relax/Living”, “Bedroom”.
- Don’t impose a single rigid color/brightness curve on the whole house.

---

### 5.3. Other Environments (Very Briefly)

- **Healthcare / elder care:**
  - Emphasize **strong morning daytime exposure** and **strict low-light evenings** to stabilize circadian rhythms.
- **Night-shift / control rooms:**
  - Special-case designs focusing on either maintaining night alertness or enabling phase shifts.
  - Use spectral tuning more aggressively and carefully.

---

## 6. Implementing This in a Control System

### 6.1. Define Per-Phase Targets

For each phase (e.g. “Morning”, “Midday”, “Afternoon”, “Evening”, “Night”), define:

- **Target CCT range**  
  Example: Morning 4000–5500K, Midday 4500–6000K, Evening 2200–3000K.
- **Target brightness range at the eye** (or a proxy based on fixture output/sensors).
- **Upper comfort limits** for brightness (to avoid glare and fatigue).

### 6.2. Daylight Integration

- Install **daylight sensors** where possible.
- For each zone:
  1. Measure current light.
  2. Compare to the target for the current phase.
  3. Adjust electric lighting in **small steps** (e.g. every 1–5 minutes).
  4. Use a **deadband** (±10–20%) so the system doesn’t “hunt” when clouds pass.

### 6.3. Balance Circadian and Aesthetic Goals

Lighting designers often compromise between biology and how the space feels:

- Cap **max CCT** in residential spaces to ~**5000K** so it doesn’t feel too clinical.
- Use **3500–4000K** as a “soft daylight” for many living spaces.
- Prefer **indirect and wall-wash light** to raise eye-level light without harsh contrast.

### 6.4. User Modes

Define clear modes that users can understand:

- **Circadian (default):**  
  Follows the daily schedule with slow changes.
- **Focus:**  
  Temporarily raises brightness and CCT (within comfort limits) for e.g. 60–90 minutes, then gradually returns to Circadian.
- **Relax / Evening:**  
  Forces very warm, dim light. Should never *increase* melanopic exposure late at night.
- **Away / Energy Save:**  
  Most lights off except necessary security or path lights.

---

## 7. Direct Answers to Key Questions

### 7.1. Should light temperature/brightness be adjusted for cloudy vs. sunny days?

- **Brightness: Yes, in a controlled way.**
  - Use daylight sensing to:
    - Reduce electric lighting when daylight is strong.
    - Boost electric lighting when daylight is weak so daytime circadian targets are still met.
- **CCT: Mostly no.**
  - Base CCT on **time-of-day and activity**, not sky condition.
  - Do not let overcast days make interiors perpetually “evening-like”.

### 7.2. Should the program be adjusted based on season?

- **Yes, modestly.**
  - Keep the **same overall pattern** (morning ramp → bright midday → softer afternoon → warm/dim evening).
  - In winter:
    - Extend the **“bright” period** and allow higher electric brightness.
  - In summer:
    - Use shades and dimming to control glare while staying above minimum daytime targets.

### 7.3. Should different environments use different programs (work vs. home)?

- **Absolutely yes.**

**Offices / Workspaces:**

- High daytime melanopic exposure (≥ ~200–250 melanopic lux at eye).
- CCT 4000–6500K by day, gently reducing later.
- Strong emphasis on vertical illuminance, uniformity, and glare control.

**Homes:**

- Per-room programs:
  - Work-like spaces closer to office patterns.
  - Living and bedrooms strongly emphasize:
    - Very warm, dim evenings.
    - Minimal night light to protect sleep.

---

## 8. Summary

1. **Biology cares about circadian-effective light at the eye**, not just “Kelvin” and “lumens.”
2. Use a **simple, smooth daily schedule**: cool/bright days, warm/dim evenings, dark nights.
3. **Use outdoor/daylight only as a guide for brightness**, not for copying sky color.
4. **Adjust by season** mainly to compensate for changing daylight, not to change the basic pattern.
5. **Different environments need different curves**, especially offices vs. homes.
6. Provide **clear modes** (Circadian, Focus, Relax, Away) and **slow transitions** so the system feels natural and non-annoying.

This gives you a practical framework you can translate into scenes, schedules, or JSON logic for whatever control platform you’re using.

# Circadian Rhythm Logic & Algorithms
**Component:** Circadian Engine
**Version:** 1.0

## 1. Functional Algorithm (The "Engine")
**Goal:** The engine runs as a background service to continuously calculate the "Virtual Target State" for all circadian-enabled groups based on the current time of day.

### Core Logic Loop
The engine executes the following logic cycle every **60 seconds**:

1.  **Get Current Time:** Fetch local system time ($T_{now}$).
2.  **Fetch Profile:** For each Group, identify the active `Circadian Profile` (set of curve points).
3.  **Locate Interval:** Find the two profile points ($P_1, P_2$) that bracket $T_{now}$ (where $P_1.time \le T_{now} < P_2.time$).
4.  **Calculate Progress:** Determine the normalized progress factor $t$ (0.0 to 1.0) between $P_1$ and $P_2$.
    $$t = \frac{T_{now} - P_1.time}{P_2.time - P_1.time}$$
5.  **Interpolate Values:** Calculate targets based on the profile's `interpolation_type`.
    * **Linear:** $Value = P_1.value + (P_2.value - P_1.value) \times t$
    * **Cosine (Smooth):** Use cosine interpolation for a natural "ease-in/ease-out" transition.
      $$Value = P_1.value + (P_2.value - P_1.value) \times \frac{1 - \cos(t \times \pi)}{2}$$
6.  **Apply to State:**
    * If Group is **Active (Auto Mode)**: Update the Group's `Target Brightness` and `Target CCT` immediately.
    * If Group is **Suspended (Manual Mode)**: Do *not* update the hardware, but calculate and store the "Virtual Target" internally so the system knows where to jump back to upon resumption.

**Boundary Condition Logic:**
* The curve is treated as a 24-hour loop.
* If the last point is *not* 23:59 or 00:00, the engine must wrap around to interpolate between the *Last Point* of the day and the *First Point* of the next day.

## 2. Control Logic Truth Table (Auto/Manual Behavior)
**Definition:** This table defines how the system handles conflicts between the automated Circadian Engine and manual user inputs (Standard Switches, Rotary Dimmers, or UI Sliders).

| Current Mode | Trigger Event | **Action** | **New Mode** |
| :--- | :--- | :--- | :--- |
| **Active (Auto)** | Timer Tick (e.g., 10:00 AM) | Update Lights to Curve Value | **Active (Auto)** |
| **Active (Auto)** | User adjusts **Brightness** | Stop Auto Updates. Apply User Brightness. | **Suspended** |
| **Active (Auto)** | User adjusts **CCT** | Stop Auto Updates. Apply User CCT. | **Suspended** |
| **Active (Auto)** | User toggles **OFF** | Turn Lights OFF. (System remembers "Active" state) | **Active (Auto)** |
| **Suspended** | Timer Tick | Calculate internal target only. Do NOT update lights. | **Suspended** |
| **Suspended** | User adjusts Dimmer again | Apply User Value. | **Suspended** |
| **Suspended** | User toggles **OFF** | Turn Lights OFF. | **Suspended** |
| **Suspended** | User clicks **"Resume"** (UI) | Fade to current Internal Target (Curve Value). | **Active (Auto)** |
| **Suspended** | System Reboot | Maintain "Suspended" flag from persistence. | **Suspended** |
| **Suspended** | **Midnight Reset** (Config=True) AND Time=00:00 | Fade to Night Curve Value. | **Active (Auto)** |