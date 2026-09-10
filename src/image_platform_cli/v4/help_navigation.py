"""Offline navigation over the actual V4 parser, with V4-specific guidance."""

import argparse
import sys
from collections.abc import Sequence

# Examples are parsed by tests, never executed. Replace local paths and server IDs.
TOPICS: dict[str, tuple[str, str]] = {
    "": (
        "Browse Native API V4 commands. image and image4 use the same implementation.",
        "help edit",
    ),
    "help": ("Navigate offline without authentication or an API request.", "help edit raster"),
    "auth": ("Manage the local public OAuth client session.", "auth status"),
    "auth login": ("Sign in using the browser device flow; --scope may be repeated.", "auth login"),
    "auth status": ("Show local session identity without exposing tokens.", "auth status"),
    "auth logout": ("Remove the locally stored session.", "auth logout"),
    "capabilities": (
        "Inspect advertised API capabilities; availability is server-specific.",
        "capabilities --json",
    ),
    "model-profiles": ("Inspect registry-backed model profiles.", "model-profiles --json"),
    "prompt": ("Prepare a prompt through the native prompt planner.", "help prompt optimize"),
    "prompt optimize": (
        "Print an optimized prompt; --json includes the validated plan.",
        'prompt optimize "a coastal cottage" --seed 17',
    ),
    "generate": (
        "Generate an image and download its verified output. Use a new output path.",
        'generate "a coastal cottage" --seed 17 -o cottage.png',
    ),
    "edit": (
        "Choose model-backed editing, deterministic programs, or raster recipes.",
        "help edit image-to-image",
    ),
    "edit image-to-image": (
        "Describe the desired final image, not an editing instruction. Staging uses typed VAE encode, latent denoise and decode internally; there are no public VAE-stage or optimizer switches.",
        'edit image-to-image "watercolor coastal cottage" --input sketch.png -o watercolor.png --seed 17 --steps 10 --width 256 --height 256',
    ),
    "edit inpaint": (
        "Repaint white mask pixels; preserve black pixels. Safety overrides require server permission.",
        'edit inpaint "a red door" --input house.png --mask door.png --output painted.png --seed 17',
    ),
    "edit segment": (
        "Select by text, box or points; provide at least one distinct output path.",
        'edit segment --input scene.png --text "house" --mask-output house-mask.png',
    ),
    "edit matte-portrait": (
        "Refine a supplied person mask to fractional alpha without changing source RGB.",
        "edit matte-portrait --input portrait.png --person-mask person.png -o matte.png",
    ),
    "edit run": (
        "Execute a deterministic-edit-v1 program; --dry-run validates locally without API access.",
        "edit run --program edit.json --input scene=scene.png --dry-run",
    ),
    "edit verify": (
        "Execute a deterministic program twice and compare output and receipt evidence.",
        "edit verify --program edit.json --input scene=scene.png",
    ),
    "edit replace-object": (
        "Replace mask coverage while preserving pixels outside it.",
        "edit replace-object --base scene.png --replacement new.png --mask object.png --dry-run",
    ),
    "edit replace-background": (
        "Invert the foreground mask once to replace the background.",
        "edit replace-background --base scene.png --replacement sky.png --mask foreground.png --dry-run",
    ),
    "edit composite": (
        "Composite an overlay with an affine matrix and optional mask.",
        "edit composite --background scene.png --overlay overlay.png -o composite.png",
    ),
    "edit convert": (
        "Convert PNG, JPEG or WebP using the deterministic conversion route.",
        "edit convert --input scene.png --format webp -o scene.webp",
    ),
    "edit raster": (
        "Build CPU raster recipes. --dry-run builds the program locally; execution uses the API.",
        "help edit raster crop",
    ),
    "edit raster crop": (
        "Crop a top-left-origin x,y,width,height rectangle.",
        "edit raster crop --input scene.png --rect 10,20,128,128 --dry-run",
    ),
    "edit raster grayscale": (
        "Convert visible pixels to equal RGB channels.",
        "edit raster grayscale --input scene.png --dry-run",
    ),
    "edit raster filter": (
        "Apply Gaussian blur, box blur or unsharp masking.",
        "edit raster filter --input scene.png --kind gaussian_blur --radius 2 --dry-run",
    ),
    "edit raster shape": (
        "Draw a rectangle or ellipse using RGBA fill and stroke colors.",
        "edit raster shape --input scene.png --kind rectangle --rect 10,10,64,64 --fill 255,0,0,255 --dry-run",
    ),
    "edit raster text": (
        "Use a registered font ID and its exact SHA-256; arbitrary font files are not accepted.",
        "edit raster text Hello --input scene.png --position 10,10 --font-id FONT_ID --font-sha256 FONT_SHA256 --font-size 24 --fill 0,0,0,255 --dry-run",
    ),
    "edit raster color-match": (
        "Match colors to an explicit reference image.",
        "edit raster color-match --input scene.png --reference reference.png --dry-run",
    ),
    "edit raster project-quad": (
        "Project a texture onto four destination corners.",
        "edit raster project-quad --input scene.png --texture poster.png --destination 0,0,128,0,128,128,0,128 --dry-run",
    ),
    "edit raster resize": (
        "Resize to dimensions; --fit contains the image within a canvas.",
        "edit raster resize --input scene.png --width 256 --height 256 --fit --dry-run",
    ),
    "edit raster flip": (
        "Mirror horizontally or vertically.",
        "edit raster flip --input scene.png --axis horizontal --dry-run",
    ),
    "edit raster rotate": (
        "Rotate by 90, 180 or 270 degrees.",
        "edit raster rotate --input scene.png --degrees 90 --dry-run",
    ),
    "edit raster canvas": (
        "Place the image on a bounded canvas at x,y.",
        "edit raster canvas --input scene.png --width 512 --height 512 --x 10 --y 10 --dry-run",
    ),
    "edit raster adjust": (
        "Compose hue, saturation, white balance and tone adjustments in a fixed order.",
        "edit raster adjust --input scene.png --hue 15 --contrast 1.05 --dry-run",
    ),
    "edit raster auto-crop": (
        "Derive crop coverage from an explicit mask and threshold.",
        "edit raster auto-crop --input scene.png --mask object.png --dry-run",
    ),
    "edit raster mesh": (
        "Warp a texture with a saved vertex/triangle mesh specification.",
        "edit raster mesh --input scene.png --texture texture.png --mesh-spec mesh.json --dry-run",
    ),
    "job": ("Inspect and cancel durable jobs and discover previews.", "job list --limit 10"),
    "job list": (
        "List jobs with repeatable status and operation filters.",
        "job list --status running --limit 10",
    ),
    "job show": ("Show one job's current state.", "job show JOB_ID"),
    "job cancel": ("Request cancellation of one job.", "job cancel JOB_ID"),
    "job previews": ("List preview outputs for a job.", "job previews JOB_ID"),
    "job preview-access": (
        "Request access to one named preview output.",
        "job preview-access JOB_ID STEP_ID OUTPUT_NAME",
    ),
    "artifact": (
        "Upload, inspect, download and delete principal-owned artifacts.",
        "artifact list --limit 10",
    ),
    "artifact list": (
        "Filter artifacts by state, kind, namespace or creation time.",
        "artifact list --kind image --limit 10",
    ),
    "artifact show": ("Show metadata for one artifact.", "artifact show ARTIFACT_ID"),
    "artifact delete": (
        "Tombstone an unreferenced artifact; confirm its ID, or explicitly use --force.",
        "artifact delete ARTIFACT_ID",
    ),
    "artifact download": (
        "Download and verify an artifact into a new local file.",
        "artifact download ARTIFACT_ID -o artifact.png",
    ),
    "artifact upload": (
        "Upload a local image or mask into a namespace.",
        "artifact upload scene.png --kind image",
    ),
    "search": (
        "Search by text, local image or artifact reference.",
        'search "coastal cottage" --limit 5',
    ),
    "caption": (
        "Caption a local image or artifact; --capture-input persists a local input first.",
        "caption scene.png --json",
    ),
    "batch": (
        "Plan, execute, evaluate and inspect bounded generation campaigns.",
        "help batch plan",
    ),
    "batch plan": (
        "Create a bounded candidate plan from an intent.",
        'batch plan "two coastal cottages" --count 2 --seed 17 --json',
    ),
    "batch run": (
        "Execute a saved plan with an explicit maximum cost.",
        "batch run PLAN_ID --max-cost 0.24",
    ),
    "batch iterate": (
        "Run bounded evaluation/revision rounds with cost and score limits.",
        "batch iterate PLAN_ID --max-cost 0.24 --threshold 0.8 --max-rounds 3",
    ),
    "batch status": ("Show the current campaign state.", "batch status CAMPAIGN_ID"),
    "batch evaluate": (
        "Read campaign evaluation scores and reasons.",
        "batch evaluate CAMPAIGN_ID",
    ),
    "batch results": (
        "Print campaign result metadata; use artifact download to save images.",
        "batch results CAMPAIGN_ID",
    ),
    "batch cancel": ("Request cancellation of a campaign.", "batch cancel CAMPAIGN_ID"),
}


def children(command: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return {
        name: child
        for action in command._actions
        if isinstance(action, argparse._SubParsersAction)
        for name, child in action.choices.items()
    }


def show_help(root: argparse.ArgumentParser, topic: Sequence[str]) -> int:
    selected = root
    for index, name in enumerate(topic):
        available = children(selected)
        if name not in available:
            print(
                f"error: unknown help topic {' '.join(topic[: index + 1])}; "
                f"available: {', '.join(available) or 'none'}",
                file=sys.stderr,
            )
            return 2
        selected = available[name]
    key = " ".join(topic).replace("edit i2i", "edit image-to-image", 1)
    guidance, example = TOPICS.get(key, ("Inspect the available options.", f"help {key}"))
    sections = [
        selected.format_help().rstrip(),
        f"GUIDANCE\n{guidance}",
        "EXAMPLES (replace paths and IDs as needed)\n  image " + example,
    ]
    entries = children(selected)
    if entries:
        sections.append(
            "TOPICS\n" + "\n".join(f"  image help {' '.join((*topic, name))}" for name in entries)
        )
    if topic:
        sections.append("RELATED\n  " + " ".join(("image", "help", *topic[:-1])))
    print("\n\n".join(sections))
    return 0
