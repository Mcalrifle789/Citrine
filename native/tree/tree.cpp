/*
 * tree — generates the blueberry tree the Citrine logo launches from.
 *
 * The tree is grown, not drawn. A recursive branching model produces a few
 * hundred tapered segments, then hangs foliage and fruit off the terminals.
 * Hand-drawing something with this much structure is slow to author and
 * impossible to re-tune; growing it means the silhouette can be changed by
 * moving one number.
 *
 * Output is SVG on stdout, for three reasons: it stays a few KB rather than
 * the megabytes an uncompressed raster of this size would cost, it stays sharp
 * at any window size, and its fills are CSS-addressable so the tree recolours
 * with the Citrine theme instead of being baked to one palette.
 *
 * The program also chooses the branch the logo departs from and reports that
 * tip as `data-anchor-x` / `data-anchor-y` on the root element, in stage units.
 * scripts/gen_launch_assets.py reads those back out and feeds them to the
 * trajectory solver, so the flight always starts from where the branch actually
 * ended up — the two generators cannot drift apart.
 *
 * Build: see scripts/build_native.py (C++17, no dependencies).
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr double kPi = 3.14159265358979323846;

/* ------------------------------------------------------------------- rng */

/*
 * splitmix64, written out rather than taken from <random>.
 *
 * std::mt19937 is specified bit-for-bit, but the distribution templates that
 * make it usable are not — two standard libraries can map the same stream to
 * different doubles. A committed asset has to regenerate identically on any
 * machine, so the whole path from seed to number is pinned here.
 */
class Rng {
public:
    explicit Rng(uint64_t seed) : state_(seed) {}

    uint64_t next()
    {
        state_ += 0x9E3779B97F4A7C15ULL;
        uint64_t z = state_;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }

    /* Uniform in [0, 1). The top 53 bits are the mantissa of a double. */
    double unit() { return static_cast<double>(next() >> 11) * 0x1.0p-53; }

    double range(double lo, double hi) { return lo + (hi - lo) * unit(); }

    int rangeInt(int lo, int hi) /* inclusive */
    {
        if (hi <= lo) return lo;
        return lo + static_cast<int>(next() % static_cast<uint64_t>(hi - lo + 1));
    }

private:
    uint64_t state_;
};

/* --------------------------------------------------------------- geometry */

struct Vec2 {
    double x = 0.0;
    double y = 0.0;
};

struct Segment {
    Vec2 base;
    Vec2 control; /* quadratic bezier handle — branches bow, they do not kink */
    Vec2 tip;
    double width = 0.0;
    int depth = 0;
};

struct Leaf {
    Vec2 at;
    double rx = 0.0;
    double ry = 0.0;
    double rotation = 0.0;
    double opacity = 1.0;
};

struct Berry {
    Vec2 at;
    double radius = 0.0;
    double ripeness = 1.0; /* 0 = pale green, 1 = fully blue */
};

struct Tree {
    std::vector<Segment> segments;
    std::vector<Leaf> leaves;
    std::vector<Berry> berries;
    std::vector<Vec2> terminals; /* candidate release points */
};

struct Config {
    double width = 1600.0;
    double height = 1000.0;
    double rootX = 0.30;   /* trunk base, fraction of width */
    double rootY = 0.97;   /* trunk base, fraction of height */
    double trunkLength = 250.0;
    double trunkWidth = 26.0;
    int maxDepth = 6;
    uint64_t seed = 20260929ULL;
    /* Where the logo should launch from, as a hint. The nearest real branch
     * tip wins, so the anchor is always somewhere a branch actually reaches. */
    double anchorHintX = 0.30;
    double anchorHintY = 0.24;
};

/* ----------------------------------------------------------------- growth */

/*
 * Grow one branch and its children.
 *
 * `angle` is measured from straight up, positive clockwise. Each level loses
 * length and width and gains angular spread, which is the whole of the model —
 * everything that makes it look like a tree rather than a fractal comes from
 * the jitter applied to those three numbers.
 */
void grow(Tree &tree, Rng &rng, const Config &cfg, Vec2 base, double angle,
          double length, double width, int depth)
{
    if (depth > cfg.maxDepth || length < 4.0) return;

    const double tipAngle = angle + rng.range(-0.08, 0.08);
    Vec2 tip{base.x + std::sin(tipAngle) * length,
             base.y - std::cos(tipAngle) * length};

    /* Bow the branch sideways from its chord. Real branches are never
     * straight, and the bow is what keeps the silhouette from looking
     * like a wire diagram. */
    const double bow = rng.range(-0.22, 0.22) * length;
    const Vec2 mid{(base.x + tip.x) * 0.5, (base.y + tip.y) * 0.5};
    Vec2 control{mid.x + std::cos(tipAngle) * bow, mid.y + std::sin(tipAngle) * bow};

    tree.segments.push_back(Segment{base, control, tip, width, depth});

    if (depth == cfg.maxDepth) {
        tree.terminals.push_back(tip);

        /* Foliage: a loose cluster rather than one blob, so the canopy edge
         * is ragged where it meets the background. */
        const int leafCount = rng.rangeInt(3, 5);
        for (int i = 0; i < leafCount; i++) {
            const double spread = rng.range(0.0, 22.0);
            const double around = rng.range(0.0, 2.0 * kPi);
            Leaf leaf;
            leaf.at = Vec2{tip.x + std::cos(around) * spread,
                           tip.y + std::sin(around) * spread * 0.78};
            leaf.rx = rng.range(18.0, 34.0);
            leaf.ry = leaf.rx * rng.range(0.52, 0.76);
            leaf.rotation = rng.range(-70.0, 70.0);
            leaf.opacity = rng.range(0.55, 0.95);
            tree.leaves.push_back(leaf);
        }

        /* Fruit hangs *below* its branch tip — gravity is the cheapest cue
         * that these are berries and not just dots. */
        const int berryCount = rng.rangeInt(0, 2);
        for (int i = 0; i < berryCount; i++) {
            Berry berry;
            berry.at = Vec2{tip.x + rng.range(-17.0, 17.0),
                            tip.y + rng.range(4.0, 25.0)};
            berry.radius = rng.range(4.0, 7.6);
            berry.ripeness = rng.unit();
            tree.berries.push_back(berry);
        }
        return;
    }

    /* Two children usually, three occasionally — a constant branching factor
     * reads as artificial almost immediately. */
    const int children = rng.unit() < 0.24 ? 3 : 2;
    const double spread = 0.42 + 0.030 * depth;

    for (int i = 0; i < children; i++) {
        const double offset = (children == 2)
            ? (i == 0 ? -spread : spread)
            : (i - 1) * spread;

        const double childAngle = tipAngle + offset * rng.range(0.66, 1.34);
        const double childLength = length * rng.range(0.66, 0.82);
        const double childWidth = std::max(1.1, width * rng.range(0.58, 0.72));

        grow(tree, rng, cfg, tip, childAngle, childLength, childWidth, depth + 1);
    }
}

Tree growTree(const Config &cfg)
{
    Tree tree;
    Rng rng(cfg.seed);

    const Vec2 root{cfg.rootX * cfg.width, cfg.rootY * cfg.height};
    grow(tree, rng, cfg, root, rng.range(-0.06, 0.06), cfg.trunkLength,
         cfg.trunkWidth, 0);

    return tree;
}

/*
 * Pick the branch tip closest to the requested anchor hint.
 *
 * Returns the tip in absolute SVG units. The caller converts to stage units.
 */
Vec2 chooseAnchor(const Tree &tree, const Config &cfg)
{
    const Vec2 hint{cfg.anchorHintX * cfg.width, cfg.anchorHintY * cfg.height};

    Vec2 best = hint;
    double bestDistance = 1e30;

    for (const Vec2 &tip : tree.terminals) {
        const double dx = tip.x - hint.x;
        const double dy = tip.y - hint.y;
        const double distance = dx * dx + dy * dy;
        if (distance < bestDistance) {
            bestDistance = distance;
            best = tip;
        }
    }
    return best;
}

/* ------------------------------------------------------------------- svg */

std::string number(double value)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%.1f", value);
    return std::string(buffer);
}

/*
 * Emit the tree as SVG.
 *
 * Segments are drawn thickest-first so trunk joins sit under their children,
 * and everything carries a class rather than a literal colour — the palette
 * lives in CSS next to the rest of the theme.
 */
void emitSvg(const Tree &tree, const Config &cfg, Vec2 anchor)
{
    std::printf(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 %.0f %.0f\" "
        "class=\"bt-tree\" role=\"img\" aria-label=\"A blueberry tree\" "
        "data-anchor-x=\"%.6f\" data-anchor-y=\"%.6f\" "
        "data-generator=\"native/tree/tree.cpp\" data-seed=\"%llu\">\n",
        cfg.width, cfg.height, anchor.x / cfg.width, anchor.y / cfg.height,
        static_cast<unsigned long long>(cfg.seed));

    /* Branches, thickest first. */
    std::vector<const Segment *> ordered;
    ordered.reserve(tree.segments.size());
    for (const Segment &segment : tree.segments) ordered.push_back(&segment);
    std::stable_sort(ordered.begin(), ordered.end(),
                     [](const Segment *a, const Segment *b) {
                         return a->width > b->width;
                     });

    std::printf("  <g class=\"bt-branches\" fill=\"none\" stroke-linecap=\"round\">\n");
    for (const Segment *segment : ordered) {
        std::printf(
            "    <path class=\"bt-branch\" data-depth=\"%d\" "
            "stroke-width=\"%s\" d=\"M%s %s Q%s %s %s %s\"/>\n",
            segment->depth, number(segment->width).c_str(),
            number(segment->base.x).c_str(), number(segment->base.y).c_str(),
            number(segment->control.x).c_str(), number(segment->control.y).c_str(),
            number(segment->tip.x).c_str(), number(segment->tip.y).c_str());
    }
    std::printf("  </g>\n");

    /* Canopy and fruit share a group so one CSS rule can sway both. */
    std::printf("  <g class=\"bt-canopy\">\n");

    std::printf("    <g class=\"bt-foliage\">\n");
    for (const Leaf &leaf : tree.leaves) {
        std::printf(
            "      <ellipse class=\"bt-leaf\" cx=\"%s\" cy=\"%s\" rx=\"%s\" "
            "ry=\"%s\" opacity=\"%.2f\" transform=\"rotate(%.1f %s %s)\"/>\n",
            number(leaf.at.x).c_str(), number(leaf.at.y).c_str(),
            number(leaf.rx).c_str(), number(leaf.ry).c_str(), leaf.opacity,
            leaf.rotation, number(leaf.at.x).c_str(), number(leaf.at.y).c_str());
    }
    std::printf("    </g>\n");

    std::printf("    <g class=\"bt-berries\">\n");
    for (const Berry &berry : tree.berries) {
        std::printf(
            "      <circle class=\"bt-berry\" cx=\"%s\" cy=\"%s\" r=\"%s\" "
            "data-ripeness=\"%.2f\"/>\n",
            number(berry.at.x).c_str(), number(berry.at.y).c_str(),
            number(berry.radius).c_str(), berry.ripeness);
        /* A single offset highlight is the difference between a circle and
           something spherical. */
        std::printf(
            "      <circle class=\"bt-berry-gleam\" cx=\"%s\" cy=\"%s\" r=\"%s\"/>\n",
            number(berry.at.x - berry.radius * 0.32).c_str(),
            number(berry.at.y - berry.radius * 0.34).c_str(),
            number(berry.radius * 0.30).c_str());
    }
    std::printf("    </g>\n");

    /* The mark the logo departs from. The renderer fades this out on release,
       so the logo reads as having *been* the berry rather than replacing it. */
    std::printf(
        "    <circle id=\"bt-anchor\" class=\"bt-anchor\" cx=\"%s\" cy=\"%s\" "
        "r=\"9\"/>\n",
        number(anchor.x).c_str(), number(anchor.y).c_str());

    std::printf("  </g>\n");
    std::printf("</svg>\n");
}

double argDouble(int argc, char **argv, const char *name, double fallback)
{
    for (int i = 1; i + 1 < argc; i++) {
        if (std::strcmp(argv[i], name) == 0) return std::atof(argv[i + 1]);
    }
    return fallback;
}

void usage(const char *program)
{
    std::fprintf(stderr,
                 "usage: %s [options]\n"
                 "  --width F       viewBox width (default 1600)\n"
                 "  --height F      viewBox height (default 1000)\n"
                 "  --seed N        growth seed (default 20260929)\n"
                 "  --depth N       recursion depth (default 8)\n"
                 "  --anchor-x F    release point hint, stage units (default 0.30)\n"
                 "  --anchor-y F    release point hint, stage units (default 0.24)\n",
                 program);
}

} // namespace

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        if (std::strcmp(argv[i], "--help") == 0 || std::strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        }
    }

    Config cfg;
    cfg.width = argDouble(argc, argv, "--width", cfg.width);
    cfg.height = argDouble(argc, argv, "--height", cfg.height);
    cfg.trunkLength = argDouble(argc, argv, "--trunk-length", cfg.trunkLength);
    cfg.trunkWidth = argDouble(argc, argv, "--trunk-width", cfg.trunkWidth);
    cfg.maxDepth = static_cast<int>(argDouble(argc, argv, "--depth", cfg.maxDepth));
    cfg.seed = static_cast<uint64_t>(
        argDouble(argc, argv, "--seed", static_cast<double>(cfg.seed)));
    cfg.anchorHintX = argDouble(argc, argv, "--anchor-x", cfg.anchorHintX);
    cfg.anchorHintY = argDouble(argc, argv, "--anchor-y", cfg.anchorHintY);

    /* Depth is exponential in both time and output size; 12 already produces
     * thousands of segments, and nothing past that is visible at render size. */
    if (cfg.maxDepth < 1 || cfg.maxDepth > 12) {
        std::fprintf(stderr, "tree: --depth must be between 1 and 12\n");
        return 2;
    }
    if (cfg.width <= 0.0 || cfg.height <= 0.0) {
        std::fprintf(stderr, "tree: --width and --height must be positive\n");
        return 2;
    }

    const Tree tree = growTree(cfg);
    if (tree.terminals.empty()) {
        std::fprintf(stderr, "tree: growth produced no branch tips\n");
        return 1;
    }

    const Vec2 anchor = chooseAnchor(tree, cfg);

    std::fprintf(stderr,
                 "tree: %zu branches, %zu leaves, %zu berries, anchor at "
                 "(%.4f, %.4f)\n",
                 tree.segments.size(), tree.leaves.size(), tree.berries.size(),
                 anchor.x / cfg.width, anchor.y / cfg.height);

    emitSvg(tree, cfg, anchor);
    return 0;
}
