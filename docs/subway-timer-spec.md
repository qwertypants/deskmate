# Subway timer spec

## Goal

At a glance, answer: **“If I leave now, I’ll be at my last stop at X:XX.”** The estimate helps Wilkins decide whether that arrival time works for the day. The apps must not require a manually entered arrival deadline or decide when he should leave.

## Trip to estimate

- Start at the apartment and estimate a **6-minute walk** to 135th Street station.
- At 135th Street, consider the **3 train first** and the **2 train** as another option. Both serve the same direction and relevant route for this trip.
- Include the transfer to the **7 train at Times Sq–42 St**.
- Estimate arrival at the 7 train’s **34 St–Hudson Yards** station.

The 6-minute walk is an initial estimate. Wilkins walks quickly and may take less time; refine this estimate later using observations from app use.

## App responsibilities

### `subway_trains`

Show when the 3 and 2 are expected at 135th Street, with the 3 first. This view answers which trains are coming to the station.

### `subway_eta`

For each train option that can be caught by leaving now, show the estimated time Wilkins would reach 34 St–Hudson Yards if he leaves now, walks to 135th Street, and takes that train. Include the transfer to the 7 in the estimate. This view answers the trip outcome, not just the first train’s arrival time.

## Data reliability

- Show the best available arrival estimate when the train data is unreliable but still sufficient to calculate a rough estimate.
- In that case, show the device’s `attentionwarning` icon and brief text explaining why the data warrants a warning.
- If there is not enough data to make a meaningful estimate, say that no estimate is available.
- Warn only about unreliable data. Do not warn based on the user’s desired arrival time or the risk of being late.

## Out of scope

- No manual target-arrival-time setting.
- No “leave by” recommendation or late/early judgment.
- No ranking trains by which gets the user there sooner; present the 3 first as the usual preference, plus the 2 when catchable.

## Handoff note

The intent is confirmed. When implementing, verify the exact transit data available for train arrivals, transfers, and end-to-end travel estimates. Define the reliability conditions from that data source, while preserving the behavior above.
