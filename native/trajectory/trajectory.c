/*
 * trajectory — the physics behind Citrine's launch animation.
 *
 * The logo detaches from a branch of the blueberry tree, arcs out, falls,
 * bounces, and settles. Hand-authored CSS keyframes cannot make that read as
 * real: the giveaway is always that the arc is a symmetric parabola, the
 * bounces are evenly spaced, and the scale ramps linearly. So the motion is
 * integrated here instead and baked into a keyframe table.
 *
 * Two things justify a solver rather than a formula:
 *
 *   1. Quadratic air drag (F = -k|v|v) has no closed-form solution, and it is
 *      exactly what makes the descent steeper than the ascent — the single
 *      strongest cue that a falling object is real.
 *   2. The landing point is a design constraint, not an output. The animation
 *      must end with the logo centred on its resting mark. So the launch
 *      velocity is *solved for* by a shooting method: integrate, measure where
 *      it lands, correct, repeat. That is a root-find wrapped around an ODE
 *      integrator, which is the kind of thing C is for.
 *
 * Output is JSON on stdout: metadata plus one sampled frame per display tick.
 *
 * Coordinates are normalised stage units — x and y both in [0, 1], y pointing
 * down to match CSS. Physics runs in metres; STAGE_METERS and the stage aspect
 * ratio convert between the two so drag and gravity stay physically meaningful
 * regardless of how large the stage is rendered.
 *
 * Build: see scripts/build_native.py (C99, no dependencies beyond libm).
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STAGE_METERS 6.0 /* the stage's height in simulated metres */

/* Integration step. Far smaller than a frame so bounce instants — which are
 * detected by a sign change, not scheduled — land on the right tick. */
#define SIM_DT 0.0002

#define MAX_SIM_SECONDS 8.0
#define MAX_FRAMES 2048

/* Below this impact speed a bounce is not worth rendering; the logo is
 * treated as having come to rest. */
#define SETTLE_SPEED 0.45

typedef struct {
    double x, y;   /* metres, y down */
    double vx, vy; /* metres/second */
} State;

typedef struct {
    double gravity;     /* m/s^2 */
    double drag;        /* quadratic drag over mass, 1/m */
    double restitution; /* fraction of normal speed kept per bounce */
    double friction;    /* fraction of tangential speed kept per bounce */
} Physics;

typedef struct {
    double t;
    double x, y;      /* normalised stage units */
    double sx, sy;    /* scale, split so squash-and-stretch can be non-uniform */
    double rotate;    /* degrees */
    double opacity;
} Frame;

typedef struct {
    Frame frames[MAX_FRAMES];
    int count;
    double duration;
    double landed_at;   /* first ground contact, seconds */
    int bounces;
    double solved_vx;   /* launch velocity the shooting method found */
    double solved_vy;
    int shoot_iterations;
} Result;

/* ---------------------------------------------------------------- helpers */

static double clamp(double v, double lo, double hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* Ken Perlin's smootherstep: zero first *and* second derivative at both ends,
 * so the growth curve has no visible corner where it starts or stops. */
static double smootherstep(double t)
{
    t = clamp(t, 0.0, 1.0);
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

/* Semi-implicit (symplectic) Euler. Velocity is updated first and the new
 * value drives the position update, which does not accumulate energy the way
 * explicit Euler does — a bouncing body stays bouncing instead of climbing. */
static void step(State *s, const Physics *p, double dt)
{
    const double speed = hypot(s->vx, s->vy);
    const double ax = -p->drag * speed * s->vx;
    const double ay = p->gravity - p->drag * speed * s->vy;

    s->vx += ax * dt;
    s->vy += ay * dt;
    s->x += s->vx * dt;
    s->y += s->vy * dt;
}

/* --------------------------------------------------------- ground contact */

/*
 * Advance one step and resolve a ground contact if the step produced one.
 *
 * Returns 1 when the body hit the ground during this step, writing the impact
 * speed through `impact_speed`. Sets `*landed` once the impact is too gentle
 * to be worth another hop.
 *
 * Both the solver and the sampling loop go through here, so there is exactly
 * one definition of what a bounce does. Duplicating the restitution rule
 * between them is how the solved landing point silently stops matching the
 * rendered one.
 */
static int step_with_ground(State *s, const Physics *p, double ground_y,
                            double dt, int *landed, double *impact_speed)
{
    step(s, p, dt);

    if (!(s->y >= ground_y && s->vy > 0.0)) return 0;

    const double speed = s->vy;
    s->y = ground_y;

    if (speed < SETTLE_SPEED) {
        s->vx = 0.0;
        s->vy = 0.0;
        if (landed) *landed = 1;
    } else {
        s->vy = -speed * p->restitution;
        s->vx *= p->friction;
    }

    if (impact_speed) *impact_speed = speed;
    return 1;
}

/* ------------------------------------------------------- shooting method */

/*
 * Integrate a launch all the way to rest and report where it stops.
 *
 * Deliberately the *resting* position rather than the first touchdown: the
 * logo bounces, and each bounce carries it further along. Solving for first
 * contact would put the animation's final frame a bounce-and-a-half past the
 * mark it is supposed to land on.
 *
 * Returns the resting x in metres, or NAN if it never comes to rest inside the
 * simulation budget.
 */
static double resting_x(const State *start, const Physics *p, double ground_y)
{
    State s = *start;
    int landed = 0;
    const int max_steps = (int)(MAX_SIM_SECONDS / SIM_DT);

    for (int i = 0; i < max_steps; i++) {
        step_with_ground(&s, p, ground_y, SIM_DT, &landed, NULL);
        if (landed) return s.x;
    }
    return NAN;
}

/*
 * Solve for the horizontal launch velocity that lands the logo on its mark.
 *
 * Secant method: two guesses, then repeatedly extrapolate the line through the
 * last two (velocity, error) pairs to its root. Landing distance is very close
 * to monotonic in launch speed here, so this converges in a handful of
 * iterations without needing a derivative.
 *
 * Writes the iteration count through `iterations` and returns the solution, or
 * the best guess reached if it stalls.
 */
static double solve_launch_vx(const State *start, const Physics *p,
                              double ground_y, double target_x, int *iterations)
{
    const double tolerance = 1e-5; /* metres — far below one rendered pixel */
    double v0 = 0.5;
    double v1 = 3.0;

    State a = *start;
    a.vx = v0;
    double f0 = resting_x(&a, p, ground_y) - target_x;

    State b = *start;
    b.vx = v1;
    double f1 = resting_x(&b, p, ground_y) - target_x;

    int i = 0;
    for (; i < 60; i++) {
        if (!isfinite(f0) || !isfinite(f1)) break;
        if (fabs(f1) < tolerance) break;

        const double denominator = f1 - f0;
        if (fabs(denominator) < 1e-12) break; /* flat secant; no better guess */

        const double v2 = v1 - f1 * (v1 - v0) / denominator;

        v0 = v1;
        f0 = f1;
        v1 = v2;

        State next = *start;
        next.vx = v1;
        f1 = resting_x(&next, p, ground_y) - target_x;
    }

    if (iterations) *iterations = i;
    return isfinite(v1) ? v1 : 0.0;
}

/* ------------------------------------------------------------ simulation */

/*
 * Run the full flight and sample it into frames.
 *
 * Everything the renderer needs is baked here, because the renderer should be
 * interpolating a table rather than reimplementing any of this in JavaScript.
 */
static void simulate(Result *out, const State *start, const Physics *p,
                     double ground_y, double start_y, double aspect,
                     double initial_scale, double spin_dps, double fps)
{
    State s = *start;

    const double meters_per_y = STAGE_METERS;
    const double meters_per_x = STAGE_METERS * aspect;
    const double frame_dt = 1.0 / fps;
    const double fall_span = ground_y - start_y;

    double t = 0.0;
    double next_sample = 0.0;
    double angle = 0.0;
    double omega = spin_dps;

    /* Squash is an impulse that decays, not a state — tracked as "how long
     * since the last impact" so it can be evaluated at sample time. */
    double impact_time = -1.0;
    double impact_strength = 0.0;

    int landed = 0;
    double landed_at = 0.0;
    double quiet_since = 0.0;

    out->count = 0;
    out->bounces = 0;

    const int max_steps = (int)(MAX_SIM_SECONDS / SIM_DT);
    for (int i = 0; i < max_steps && out->count < MAX_FRAMES; i++) {
        /* --- sample the current state into a frame, if one is due --- */
        if (t >= next_sample - 1e-9) {
            Frame *f = &out->frames[out->count++];

            f->t = t;
            f->x = s.x / meters_per_x;
            f->y = s.y / meters_per_y;

            /* Growth is driven by how far it has fallen, not by elapsed time,
             * so it reads as "it grows as it comes down" and reaches full size
             * exactly as it arrives — which is what the brief asks for. */
            const double fallen = fall_span > 1e-9 ? (s.y - start_y) / fall_span : 1.0;
            const double grown = smootherstep(clamp(fallen, 0.0, 1.0));
            const double scale = initial_scale + (1.0 - initial_scale) * grown;

            /* Airborne stretch along the direction of travel. Volume is
             * preserved (sx * sy stays ~1) so it deforms rather than swells. */
            const double speed = hypot(s.vx, s.vy);
            double stretch = 1.0 + clamp(speed / 14.0, 0.0, 0.16);
            if (landed) stretch = 1.0;

            double squash = 1.0;
            if (impact_time >= 0.0) {
                const double since = t - impact_time;
                /* ~9 Hz wobble under an exponential envelope: the decaying
                 * ring of something solid landing, not a single dent. */
                squash = 1.0 - impact_strength * exp(-9.0 * since) * cos(18.0 * since);
                squash = clamp(squash, 0.72, 1.28);
            }

            const double sy = scale * stretch * squash;
            const double sx = sy > 1e-6 ? (scale * scale) / sy : scale;

            f->sx = sx;
            f->sy = sy;
            f->rotate = angle;
            /* It emerges from the foliage rather than appearing on top of it. */
            f->opacity = clamp(t / 0.14, 0.0, 1.0);

            next_sample += frame_dt;
        }

        /* --- advance the physics --- */
        if (!landed) {
            double impact_speed = 0.0;
            const int was_landed = landed;

            if (step_with_ground(&s, p, ground_y, SIM_DT, &landed, &impact_speed)) {
                if (landed && !was_landed) {
                    landed_at = out->landed_at > 0.0 ? out->landed_at : t;
                } else {
                    out->bounces++;
                }

                if (out->landed_at <= 0.0) out->landed_at = t;

                impact_time = t;
                impact_strength = clamp(impact_speed / 26.0, 0.03, 0.26);
                omega *= 0.42;
            }

            /* Spin bleeds off through the air, then is sprung upright once
             * the logo is down — a logo that settles crooked looks broken, so
             * the end state is pinned even though the flight is free. */
            omega *= (1.0 - 0.55 * SIM_DT);
            angle += omega * SIM_DT;
        } else {
            /* Critically damped spring on the angle: returns to level without
             * overshooting past it. */
            const double stiffness = 120.0;
            const double damping = 2.0 * sqrt(stiffness);
            const double accel = -stiffness * angle - damping * omega;
            omega += accel * SIM_DT;
            angle += omega * SIM_DT;

            if (fabs(angle) < 0.05 && fabs(omega) < 0.5) {
                angle = 0.0;
                omega = 0.0;
                if (quiet_since <= 0.0) quiet_since = t;
            }
        }

        t += SIM_DT;

        /* Stop once it is down, level, and the impact wobble has rung out —
         * every frame after that is a duplicate the renderer would just sit on. */
        if (landed && quiet_since > 0.0 && t - quiet_since > 0.18 &&
            (impact_time < 0.0 || t - impact_time > 0.55)) {
            break;
        }
    }

    /* Pin the final frame exactly on the mark. The integrator lands within a
     * fraction of a pixel, but "exactly" is free here and means the animation
     * can hand off to the static layout without a jump. */
    if (out->count > 0) {
        Frame *last = &out->frames[out->count - 1];
        last->x = s.x / meters_per_x;
        last->y = ground_y / meters_per_y;
        last->sx = 1.0;
        last->sy = 1.0;
        last->rotate = 0.0;
        last->opacity = 1.0;
        out->duration = last->t;
    }

    out->landed_at = out->landed_at > 0.0 ? out->landed_at : landed_at;
}

/* ----------------------------------------------------------------- output */

static void emit_json(const Result *r, double anchor_x, double anchor_y,
                      double rest_x, double rest_y, double fps, double aspect)
{
    printf("{\n");
    printf("  \"version\": 1,\n");
    printf("  \"generator\": \"native/trajectory/trajectory.c\",\n");
    printf("  \"fps\": %.0f,\n", fps);
    printf("  \"aspect\": %.4f,\n", aspect);
    printf("  \"durationMs\": %.1f,\n", r->duration * 1000.0);
    printf("  \"landedAtMs\": %.1f,\n", r->landed_at * 1000.0);
    printf("  \"bounces\": %d,\n", r->bounces);
    printf("  \"solvedLaunchVelocity\": { \"x\": %.6f, \"y\": %.6f },\n",
           r->solved_vx, r->solved_vy);
    printf("  \"shootIterations\": %d,\n", r->shoot_iterations);
    printf("  \"anchor\": { \"x\": %.6f, \"y\": %.6f },\n", anchor_x, anchor_y);
    printf("  \"rest\": { \"x\": %.6f, \"y\": %.6f },\n", rest_x, rest_y);
    printf("  \"frames\": [\n");

    for (int i = 0; i < r->count; i++) {
        const Frame *f = &r->frames[i];
        printf("    { \"t\": %.4f, \"x\": %.5f, \"y\": %.5f, \"sx\": %.5f, "
               "\"sy\": %.5f, \"rotate\": %.3f, \"opacity\": %.4f }%s\n",
               f->t, f->x, f->y, f->sx, f->sy, f->rotate, f->opacity,
               i + 1 < r->count ? "," : "");
    }

    printf("  ]\n");
    printf("}\n");
}

/* ------------------------------------------------------------------- main */

static double arg_double(int argc, char **argv, const char *name, double fallback)
{
    for (int i = 1; i + 1 < argc; i++) {
        if (strcmp(argv[i], name) == 0) return atof(argv[i + 1]);
    }
    return fallback;
}

static void usage(const char *program)
{
    fprintf(stderr,
            "usage: %s [options]\n"
            "  --anchor-x F   branch release point, stage units (default 0.30)\n"
            "  --anchor-y F   branch release point, stage units (default 0.24)\n"
            "  --rest-x F     final resting point, stage units (default 0.50)\n"
            "  --rest-y F     final resting point, stage units (default 0.66)\n"
            "  --fps F        sample rate (default 60)\n"
            "  --aspect F     stage width / height (default 1.60)\n"
            "  --scale F      starting scale on the branch (default 0.16)\n"
            "  --spin F       initial spin, degrees/second (default -150)\n"
            "  --drag F       quadratic drag coefficient (default 0.055)\n"
            "  --restitution F  bounce energy retained (default 0.36)\n",
            program);
}

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        }
    }

    const double anchor_x = arg_double(argc, argv, "--anchor-x", 0.30);
    const double anchor_y = arg_double(argc, argv, "--anchor-y", 0.24);
    const double rest_x = arg_double(argc, argv, "--rest-x", 0.50);
    const double rest_y = arg_double(argc, argv, "--rest-y", 0.66);
    const double fps = arg_double(argc, argv, "--fps", 60.0);
    const double aspect = arg_double(argc, argv, "--aspect", 1.60);
    const double initial_scale = arg_double(argc, argv, "--scale", 0.16);
    const double spin = arg_double(argc, argv, "--spin", -150.0);

    Physics physics;
    physics.gravity = arg_double(argc, argv, "--gravity", 9.81);
    physics.drag = arg_double(argc, argv, "--drag", 0.055);
    physics.restitution = arg_double(argc, argv, "--restitution", 0.36);
    physics.friction = arg_double(argc, argv, "--friction", 0.62);

    if (fps < 1.0 || fps > 240.0) {
        fprintf(stderr, "trajectory: --fps must be between 1 and 240\n");
        return 2;
    }
    if (rest_y <= anchor_y) {
        fprintf(stderr, "trajectory: --rest-y must be below --anchor-y "
                        "(the logo has to fall)\n");
        return 2;
    }
    if (physics.restitution < 0.0 || physics.restitution >= 1.0) {
        fprintf(stderr, "trajectory: --restitution must be in [0, 1)\n");
        return 2;
    }

    const double meters_per_y = STAGE_METERS;
    const double meters_per_x = STAGE_METERS * aspect;

    State start;
    start.x = anchor_x * meters_per_x;
    start.y = anchor_y * meters_per_y;
    start.vx = 0.0;
    /* A small upward toss: the logo is flicked off the branch rather than
     * simply dropped, which is what "flies in from the tree" means. */
    start.vy = arg_double(argc, argv, "--launch-vy", -1.35);

    const double ground_y = rest_y * meters_per_y;
    const double target_x = rest_x * meters_per_x;

    int iterations = 0;
    start.vx = solve_launch_vx(&start, &physics, ground_y, target_x, &iterations);

    if (!isfinite(start.vx)) {
        fprintf(stderr, "trajectory: could not solve a launch that reaches the "
                        "resting point; check --drag and --launch-vy\n");
        return 1;
    }

    static Result result;
    result.solved_vx = start.vx;
    result.solved_vy = start.vy;
    result.shoot_iterations = iterations;

    simulate(&result, &start, &physics, ground_y, start.y, aspect,
             initial_scale, spin, fps);

    if (result.count == 0) {
        fprintf(stderr, "trajectory: simulation produced no frames\n");
        return 1;
    }

    fprintf(stderr,
            "trajectory: solved vx=%.4f m/s in %d iterations, %d frames, "
            "%d bounces, %.0f ms\n",
            result.solved_vx, iterations, result.count, result.bounces,
            result.duration * 1000.0);

    emit_json(&result, anchor_x, anchor_y, rest_x, rest_y, fps, aspect);
    return 0;
}
