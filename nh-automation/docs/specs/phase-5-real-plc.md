# Phase 5 — Real PLC Integration

> Prerequisites: phase 4 done, and OPEN-6 (PLC brand/model) and OPEN-7 answered. Read `00-overview.md` and `phase-4-plc-api-simulator.md` first.
> Goal: one real machine runs a full order through the system, then all machines.

**This spec is a placeholder. Complete it once the PLC model is known.**

## Information needed before starting
- [ ] PLC brand, model, firmware; programming software.
- [ ] Who programs the PLC (internal or contractor).
- [ ] HTTP client capabilities: GET/POST, JSON parse/generate, custom headers, HTTPS support, timeouts, retries.
- [ ] Can it persist a counter (for `seq`) and pending events across power loss?
- [ ] How it measures liters (flow meter, scale) and its precision.
- [ ] How the operator starts/stops a fill on the machine (physical buttons, HMI).
- [ ] Network: IP addressing, VLAN, can it reach the server?
- [ ] Behavior wanted when the server is down (OPEN-8).

## Expected work
1. Compare the PLC capabilities with `docs/PLC_PROTOCOL.md`; list required changes (e.g. push instead of poll, XML/CSV instead of JSON, Modbus/OPC UA gateway if HTTP is insufficient).
2. Implement protocol adaptations in the API **without changing the assignment service** (adapter layer).
3. Update the simulator to mimic the real PLC behavior.
4. Network setup with IT: machine VLAN, firewall so PLCs reach only the API.
5. Pilot on one machine: run real orders in parallel with manual control; compare PLC liters vs physical measurement.
6. Roll out to all machines; update the operator guide.

## Definition of done
- [ ] One real machine completes an order with all events recorded and correct liters.
- [ ] Recovery after a network drop verified.
- [ ] All machines connected; `docs/PROGRESS.md` updated.
