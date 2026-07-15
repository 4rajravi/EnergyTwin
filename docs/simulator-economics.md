# Simulator Economics

The simulator now separates total cost into the pieces that matter for energy-control decisions.

## Cost Components

```text
total_cost =
    energy_import_cost
  + demand_charge
  + battery_wear_cost
  - export_credit
```

## Current Defaults

| setting | default | location |
| --- | --- | --- |
| demand charge | `$3.20/kW/day` | `TariffSpec.demand_charge_usd_per_kw_day` |
| export credit | `32%` of import price | `TariffSpec.export_credit_fraction` |
| battery wear | `$0.018/kWh throughput` | `BatterySpec.wear_cost_usd_per_kwh_throughput` |

## Why This Matters

Before this change, optimization mostly chased hourly energy prices. Now the simulator can also value peak reduction and penalize unnecessary battery cycling.

This makes policy comparison more realistic:

- a controller that reduces peak demand can lower demand charges
- a controller that cycles the battery too aggressively pays wear cost
- exported solar receives partial credit rather than full retail value

The Scenario Lab dashboard shows these components as a policy cost breakdown so the tradeoff is visible without inspecting raw API JSON.

## Still Simplified

This is not yet a full utility tariff model. Future additions can include:

- monthly billing windows
- time-of-use demand charges
- demand ratchets
- battery degradation based on depth of discharge
- export limits and interconnection constraints
