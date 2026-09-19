"""Percentiles from binned (grouped) income counts.

percentile(bins, p): bins = [(lo, hi_or_None, count), ...] in ascending order.
 - inside a closed bracket: linear interpolation (uniform density within the bracket);
 - inside the open-ended top bracket: Pareto tail. alpha is estimated from the last closed
   bracket:  alpha = ln(S(lo_prev)/S(lo_top)) / ln(lo_top/lo_prev),  S(x) = share above x,
   then      x_p   = lo_top * (S(lo_top) / (1-p)) ** (1/alpha).
Returns (value, extrapolated_flag).
"""
import math


def percentile(bins, p):
    total = float(sum(c for _, _, c in bins))
    target = p * total
    cum = 0.0
    for i, (lo, hi, c) in enumerate(bins):
        if cum + c >= target and c > 0:
            if hi is not None:
                return lo + (hi - lo) * (target - cum) / c, False
            prev_lo, _, prev_c = bins[i - 1]
            s_top = c / total
            s_prev = (c + prev_c) / total
            alpha = math.log(s_prev / s_top) / math.log(lo / prev_lo)
            return lo * (s_top / (1.0 - p)) ** (1.0 / alpha), True
        cum += c
    raise ValueError("percentile not reached")


def parse_bracket(label):
    """'$5,000 to $9,999' -> (5000, 10000); 'Under $5,000 (including loss)' -> (0, 5000);
    '$100,000 and over' -> (100000, None). Returns None for non-bracket labels."""
    import re
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", label)]
    if label.startswith("Under $") and len(nums) == 1:
        return 0, nums[0]
    if label.endswith("and over") and len(nums) == 1:
        return nums[0], None
    if " to $" in label and len(nums) == 2:
        return nums[0], nums[1] + 1
    return None
