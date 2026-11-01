"""Every figure the cold-chain deck states, computed from inputs/coldchain_notes.md (rough, illustrative)."""
tam25, tam30 = 95.0, 135.0          # $bn, notes
ph25, ph30 = 21.0, 35.0             # $bn, notes
cap25, cap_g = 4.1, 0.04            # bn cubic feet, % pa
yrs = 5
def cagr(a, b): return (b / a) ** (1 / yrs) - 1
out = {}
out["total CAGR 2025-30"] = cagr(tam25, tam30); assert abs(out["total CAGR 2025-30"] - 0.0728) < 0.0005
out["pharma CAGR 2025-30"] = cagr(ph25, ph30); assert abs(out["pharma CAGR 2025-30"] - 0.1076) < 0.0005
np25, np30 = tam25 - ph25, tam30 - ph30
assert (np25, np30) == (74.0, 100.0)
out["non-pharma CAGR 2025-30"] = cagr(np25, np30); assert abs(out["non-pharma CAGR 2025-30"] - 0.0621) < 0.0005
out["market growth $bn"] = tam30 - tam25; assert out["market growth $bn"] == 40
out["pharma growth $bn"] = ph30 - ph25; assert out["pharma growth $bn"] == 14
out["non-pharma growth $bn"] = np30 - np25; assert out["non-pharma growth $bn"] == 26
out["pharma share 2025"] = ph25 / tam25; assert abs(out["pharma share 2025"] - 0.221) < 0.001
out["pharma share 2030"] = ph30 / tam30; assert abs(out["pharma share 2030"] - 0.259) < 0.001
out["pharma share of growth"] = (ph30 - ph25) / (tam30 - tam25); assert out["pharma share of growth"] == 0.35
cap30 = cap25 * (1 + cap_g) ** yrs
out["capacity 2030 bn cu ft"] = cap30; assert abs(cap30 - 4.99) < 0.01
# index paths 2025=100
idx_mkt = [round(100 * (1 + out["total CAGR 2025-30"]) ** t, 1) for t in range(6)]
idx_ph = [round(100 * (1 + out["pharma CAGR 2025-30"]) ** t, 1) for t in range(6)]
idx_cap = [round(100 * (1 + cap_g) ** t, 1) for t in range(6)]
assert idx_mkt[-1] == 142.1 and idx_ph[-1] == 166.7 and idx_cap[-1] == 121.7, (idx_mkt, idx_ph, idx_cap)
out["index market"] = idx_mkt; out["index pharma"] = idx_ph; out["index capacity"] = idx_cap
lo, hi, amb = 220, 260, 120
out["build cost multiple low"] = lo / amb; out["build cost multiple high"] = hi / amb; out["build cost multiple mid"] = (lo + hi) / 2 / amb
assert out["build cost multiple mid"] == 2.0 and round(lo / amb, 1) == 1.8 and round(hi / amb, 1) == 2.2
out["build cost premium $/sqft low"] = lo - amb; out["build cost premium $/sqft high"] = hi - amb
assert (lo - amb, hi - amb) == (100, 140)
client_rev = 1.2
out["pharma 2025 market / client revenue"] = ph25 / client_rev; assert out["pharma 2025 market / client revenue"] == 17.5
for k, v in out.items():
    print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")
print("stated: ~$95bn, ~$135bn, ~7% a year (7.3%), pharma ~$21bn -> ~$35bn, ~11% a year (10.8%), non-pharma $74bn -> $100bn, ~6% a year (6.2%)")
print("stated: +$40bn growth, pharma +$14bn = 35% of growth, 22% of 2025 market, 26% of 2030 market")
print("stated: capacity 4.1 -> ~5.0bn cu ft, index 2030: market 142, pharma 167, capacity 122")
print("stated: build cost 1.8x to 2.2x ambient, about 2x; premium $100 to $140 per sq ft")
