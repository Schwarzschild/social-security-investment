#!/usr/bin/env python3
"""Beginning-of-month annuities, valued at the end of the final month.

Social Security Simulation.

Usage: python sssim.py sssim.cfg --output-dir output
Requires matplotlib (the solver uses only Python's standard library).
"""

import argparse
import configparser
import json
import math
from pathlib import Path


def log_sum(count, x):
    """log(sum(exp(k*x), k=0..count-1)), stable even near zero."""
    if x == 0:
        return math.log(count)
    if x > 0:
        return ((count - 1) * x + math.log(-math.expm1(-count * x))
                - math.log(-math.expm1(-x)))
    return math.log(-math.expm1(count * x)) - math.log(-math.expm1(x))


def future_value(payment, months, r_month):
    """Payment at month starts; first earns months periods, last earns one."""
    if r_month == 0:
        return payment * months
    x = math.log1p(r_month)
    return math.exp(math.log(payment) + x + log_sum(months, x))


def solve_rate(p67, p70, n67, n70):
    """Find the unique nonzero real rate in r_month > -1, if one exists.

    Cancel the shared (1+r_month) from the geometric sums, not an r_month denominator.
    Bisect in x=log(1+r_month) using log(S_n67/S_n70) - log(P70/P67).
    This does not manufacture the zero root of the cross-multiplied equation.
    For n67>n70, S_n67/S_n70 increases strictly from 1 to infinity as r_month rises;
    for n67<n70 it decreases strictly from 1 to zero.
    """
    if n67 == n70:
        if p67 == p70:
            return {"status": "Every rate greater than -1 satisfies Equation 4.",
                    "monthly_rate": None, "iterations": 0}
        return {"status": "No solution: equal durations but unequal payments.",
                "monthly_rate": None, "iterations": 0}
    target = math.log(p70) - math.log(p67)
    if (n67 > n70 and p70 <= p67) or (n67 < n70 and p70 >= p67):
        return {"status": "No finite solution for i > -1.",
                "monthly_rate": None, "iterations": 0}
    if math.isclose(target, math.log(n67) - math.log(n70), rel_tol=0, abs_tol=1e-14):
        return {"status": "Only r_month = 0 satisfies Equation 4 (within numerical precision).",
                "monthly_rate": None, "iterations": 0}

    def residual(x):
        return log_sum(n67, x) - log_sum(n70, x) - target

    low, high = -1.0, 1.0
    for _ in range(60):
        if residual(low) * residual(high) <= 0:
            break
        low *= 2
        high *= 2
    else:
        raise ArithmeticError("Could not bracket a root within numerical limits.")

    f_low = residual(low)
    for iteration in range(1, 251):
        mid = (low + high) / 2
        f_mid = residual(mid)
        if abs(f_mid) < 1e-13 or high - low < 1e-14:
            break
        if f_low * f_mid <= 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    r_month = math.expm1(mid)
    if r_month <= -1 or r_month == 0:
        raise ArithmeticError("Root is too close to -1 or 0 to represent reliably.")
    fv1 = future_value(p67, n67, r_month)
    fv2 = future_value(p70, n70, r_month)
    return {"status": "Unique nonzero solution found.", "monthly_rate": r_month,
            "monthly_rate_percent": 100 * r_month, "iterations": iteration,
            "FV1_at_solution": fv1, "FV2_at_solution": fv2,
            "relative_difference": (fv2 - fv1) / max(fv1, fv2)}


def read_config(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except configparser.Error as error:
        raise ValueError(f"Invalid configuration: {error}") from error
    if "Input" not in parser:
        raise ValueError("Missing config section: [Input]")
    if any(key in parser["Input"] for key in ("P64", "P67", "P70")):
        raise ValueError("Use P_PIA instead of independent P67/P70 inputs.")
    if any(key in parser["Input"] for key in ("n", "m")):
        raise ValueError("Use n67 and n70 instead of n and m inputs.")
    config = {}
    for key in ("P_PIA", "n70", "n67", "annual_rate"):
        if key not in parser["Input"]:
            raise ValueError(f"Missing config key: {key}")
        try:
            config[key] = float(parser["Input"][key])
        except ValueError as error:
            raise ValueError(f"{key} must be a finite number.") from error
    for key in ("P_PIA", "n70", "n67", "annual_rate"):
        if key not in config:
            raise ValueError(f"Missing config key: {key}")
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number.")
    for key in ("n70", "n67"):
        if config[key] <= 0 or int(config[key]) != config[key]:
            raise ValueError(f"{key} must be a positive integer month count.")
        config[key] = int(config[key])
    if config["P_PIA"] <= 0:
        raise ValueError("P_PIA must be positive.")
    if config["annual_rate"] <= -1:
        raise ValueError("Annual rate must be greater than -1 (10% = 0.10).")
    config["P67"] = 1.00 * config["P_PIA"]
    config["P70"] = 1.24 * config["P_PIA"]
    if not all(math.isfinite(config[key]) for key in ("P67", "P70")):
        raise ValueError("Derived monthly benefits exceed numerical limits.")
    return config


# Report scenario: maximum federal taxation of benefits, Maryland exemption,
# and combined top capital-gains taxes paid only on investment growth at the endpoint.
BENEFIT_TAX_RATE = 0.85 * 0.37
CAPITAL_GAINS_TAX_RATE = 0.356


def after_tax_details(payment, months, r_month):
    """Tax each benefit before investment; tax only growth at the endpoint."""
    net_payment = payment * (1 - BENEFIT_TAX_RATE)
    principal = net_payment * months
    before_tax = future_value(net_payment, months, r_month)
    growth = before_tax - principal
    tax = CAPITAL_GAINS_TAX_RATE * max(growth, 0)
    value = before_tax - tax
    if not all(math.isfinite(x) for x in (value, tax, growth)):
        raise ArithmeticError("Endpoint tax calculation exceeds numerical limits.")
    return {"net_monthly_payment": net_payment,
            "invested_principal": principal,
            "cumulative_growth": growth,
            "cumulative_investment_tax": tax,
            "final_value": value}


def after_tax_value(payment, months, r_month):
    return after_tax_details(payment, months, r_month)["final_value"]


def tax_chart_root(config, low, high):
    """Find an after-tax crossing within the plotted monthly-rate interval."""
    def residual(r_month):
        return (after_tax_value(config["P67"], config["n67"], r_month)
                - after_tax_value(config["P70"], config["n70"], r_month))
    f_low, f_high = residual(low), residual(high)
    if f_low == 0 and f_high == 0:
        return None
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        return None
    for _ in range(60):
        mid = (low + high) / 2
        f_mid = residual(mid)
        if f_mid == 0:
            return mid
        if f_low * f_mid <= 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def make_chart(config, solution, destination, taxed=False, delta_plot=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter, FuncFormatter
    plt.rcParams["text.parse_math"] = True

    r_annual_values = [0.035 + (0.20 - 0.035) * k / 600 for k in range(601)]
    r_month_values = [math.expm1(math.log1p(r_annual) / 12) for r_annual in r_annual_values]
    value_function = after_tax_value if taxed else future_value
    first = [value_function(config["P67"], config["n67"], r_month) for r_month in r_month_values]
    second = [value_function(config["P70"], config["n70"], r_month) for r_month in r_month_values]
    r_month_root = tax_chart_root(config, r_month_values[0], r_month_values[-1]) if taxed else solution["monthly_rate"]
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    if delta_plot:
        delta_values = [fv67 - fv70 for fv67, fv70 in zip(first, second)]
        ax.plot(r_annual_values, delta_values, color="#176b93", linewidth=2.3,
                label=r"Delta: $\mathrm{FV}_{67} - \mathrm{FV}_{70}$")
        ax.axhline(0, color="#777777", linewidth=1)
    else:
        ax.plot(r_annual_values, first, color="#176b93", linewidth=2.3, label=r"$\mathrm{FV}_{67}$")
        ax.plot(r_annual_values, second, color="#d46929", linewidth=2.3, label=r"$\mathrm{FV}_{70}$")
    ax.set_xlim(0.035, 0.20)
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=2))
    ax.set_xlabel("Investment Rate")
    if delta_plot:
        ax.set_ylabel("After-tax delta ($)" if taxed else "Delta ($)")
    else:
        ax.set_ylabel("After-tax future value ($)" if taxed else "Future value ($)")
    ax.grid(True, alpha=0.2)
    if r_month_root is not None and r_month_values[0] <= r_month_root <= r_month_values[-1]:
        r_annual_root = math.expm1(12 * math.log1p(r_month_root))
        ax.axvline(r_annual_root, color="#555555", linestyle="--", linewidth=1,
                   label=f"Equal FV: {r_annual_root:.2%}/year")
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value/1e6:,.1f}M"))
    if not taxed and not delta_plot:
        ax.set_title("Future values versus annual investment rate of return", fontsize=12)
    elif not taxed and delta_plot:
        ax.set_title("Delta versus annual investment rate of return.", fontsize=12)
    elif taxed and not delta_plot:
        ax.set_title("Tax adjusted future values versus annual investment rate of return", fontsize=12)
    else:
        ax.set_title("Tax adjusted delta versus annual investment rate of return.", fontsize=12)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", type=Path,
                        default=Path(__file__).with_name("sssim.cfg"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    try:
        config = read_config(args.config)
        r_month = math.expm1(math.log1p(config["annual_rate"]) / 12)
        fv1 = future_value(config["P67"], config["n67"], r_month)
        fv2 = future_value(config["P70"], config["n70"], r_month)
        solution = solve_rate(config["P67"], config["P70"], config["n67"], config["n70"])
        result = {"inputs": {k: config[k] for k in ("P_PIA", "n70", "n67", "annual_rate")},
                  "derived_benefits": {"P67": config["P67"], "P70": config["P70"],
                                       "full_retirement_age": 67, "factor_67": 1.00, "factor_70": 1.24}, "derived_monthly_rate": r_month, "FV1": fv1, "FV2": fv2,
                  "delta_FV1_minus_FV2": fv1 - fv2, "equation_4_solution": solution}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        make_chart(config, solution, args.output_dir / "future_values.png")
        make_chart(config, solution, args.output_dir / "future_values_after_tax.png", taxed=True)
        make_chart(config, solution, args.output_dir / "delta.png", delta_plot=True)
        make_chart(config, solution, args.output_dir / "delta_after_tax.png",
                   taxed=True, delta_plot=True)
        comparisons = []
        for r_annual in (0.05, 0.10, 0.15, 0.20):
            comparison_r_month = math.expm1(math.log1p(r_annual) / 12)
            comparisons.append({
                "annual_rate": r_annual, "monthly_rate": comparison_r_month,
                "FV1": future_value(config["P67"], config["n67"], comparison_r_month),
                "FV2": future_value(config["P70"], config["n70"], comparison_r_month),
                "after_tax_FV1": after_tax_value(config["P67"], config["n67"], comparison_r_month),
                "after_tax_FV2": after_tax_value(config["P70"], config["n70"], comparison_r_month)})
        result["tax_scenario"] = {
            "benefit_tax_rate": BENEFIT_TAX_RATE,
            "capital_gains_tax_rate": CAPITAL_GAINS_TAX_RATE,
            "timing": "Income tax deducted from each monthly benefit before investment; capital-gains tax on growth only at the common endpoint (age 90 in the supplied config)",
            "configured_rate_after_tax_FV1": after_tax_value(config["P67"], config["n67"], r_month),
            "configured_rate_after_tax_FV2": after_tax_value(config["P70"], config["n70"], r_month),
            "configured_rate_after_tax_delta_FV1_minus_FV2": (
                after_tax_value(config["P67"], config["n67"], r_month)
                - after_tax_value(config["P70"], config["n70"], r_month)),
            "configured_rate_details_FV1": after_tax_details(config["P67"], config["n67"], r_month),
            "configured_rate_details_FV2": after_tax_details(config["P70"], config["n70"], r_month),
            "break_even_monthly_rate_in_chart": tax_chart_root(
                config, math.expm1(math.log1p(0.035) / 12), math.expm1(math.log1p(0.20) / 12)),
            "annual_return_comparisons": comparisons}
        (args.output_dir / "results.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, OSError, ArithmeticError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"PIA: ${config['P_PIA']:,.2f}; P67: ${config['P67']:,.2f}; P70: ${config['P70']:,.2f}")
    print(f"Configured effective annual return: {config['annual_rate']:.2%}")
    print(f"Derived monthly decimal rate: {r_month:.12f}")
    print(f"FV1 = ${fv1:,.2f}\nFV2 = ${fv2:,.2f}\nDelta = ${fv1-fv2:,.2f}")
    print(solution["status"])
    if solution["monthly_rate"] is not None:
        r_annual_root = math.expm1(12 * math.log1p(solution["monthly_rate"]))
        print(f"Nonzero effective annual break-even return: {r_annual_root:.2%}")
        print(f"FV1 at solution = ${solution['FV1_at_solution']:,.2f}")
        print(f"FV2 at solution = ${solution['FV2_at_solution']:,.2f}")
    print(f"Results and charts saved in {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
