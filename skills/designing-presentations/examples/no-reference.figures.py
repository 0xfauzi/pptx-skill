rev = {2021: 142.0, 2022: 158.5, 2023: 171.2, 2024: 186.9, 2025: 203.4}
routes = {"North Sound": (61.2, 412), "Harbour Loop": (54.8, 366), "Island Link": (47.9, 318), "Coastal Run": (39.5, 262)}
cagr = (rev[2025] / rev[2021]) ** 0.25 - 1
assert round(cagr * 100, 1) == 9.4
assert round(sum(r for r, _ in routes.values()), 1) == rev[2025] == 203.4
assert sum(p for _, p in routes.values()) == 1358
assert round(rev[2025] - rev[2021], 1) == 61.4
north_share = routes["North Sound"][0] / rev[2025]
assert round(north_share * 100) == 30
print("9.4%", "203.4", "1,358", "61.4", "30%", "96.1%", "93.4%", "2.7")
assert round(96.1 - 93.4, 1) == 2.7
