"""Offline navigation over the actual V4 parser, with V4-specific guidance."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Guide:
    guidance: str
    example: str
    details: str


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
    "model-profiles": (
        "Inspect registered profiles. Use --details for server-owned plain text guidance; --profile selects one ID.",
        "model-profiles --json",
    ),
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
        'edit image-to-image "watercolor coastal cottage" --input sketch.png -o watercolor.png --seed 17',
    ),
    "edit inpaint": (
        "Repaint white mask pixels; preserve black pixels. Safety overrides require server permission.",
        'edit inpaint "a red door" --input house.png --mask door.png --output painted.png --seed 17',
    ),
    "edit upscale": (
        "Enlarge an image through the V4 enhancement route; choose deterministic or AI quality.",
        "edit upscale --input scene.png --width 2048 --height 2048 -o enlarged.png",
    ),
    "edit restore": (
        "Restore an image at its original dimensions through the V4 enhancement route.",
        "edit restore --input scene.png --quality-tier ai -o restored.png",
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
    "edit plan": (
        "Compile a bounded deterministic edit request into a physical V4 Pipeline.",
        "edit plan --request edit-plan-request.json",
    ),
    "edit batch": (
        "Execute a bounded synchronous batch of independent deterministic edit requests.",
        "edit batch --request edit-batch-request.json",
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
    "job submit": (
        "Submit a complete Native API V4 Pipeline request with durable Job policy. Browse the help-only topics below for guided image profiles and recovery.",
        "job submit --request job-request.json",
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
    "batch list": ("List campaigns using cursor pagination.", "batch list --limit 10"),
}


# These are discoverable help pages rather than executable subcommands. They document
# profiles carried inside the generic V4 Job request without widening the CLI surface.
GUIDES: dict[str, Guide] = {
    "model-profiles usage": Guide(
        guidance="Read current model guidance from the server, as plain text or JSON.",
        example="model-profiles --profile i2i-ip-adapter-plus-sd15 --details",
        details=(
            "HELP itself is offline. --details requires authentication and a server supporting "
            "usage guidance. The text describes inputs, defaults versus recommended settings, "
            "examples, model selection limits and recovery. The CLI does not interpret or apply it.\n"
            "Use --details --json to retain the text with its profile ID and revision. "
            "Missing guidance or unsupported servers are reported, not replaced by guessed advice."
        ),
    ),
    "job submit guided-edit": Guide(
        guidance=(
            "Choose a guided image profile by the evidence you can supply. Canny ControlNet "
            "follows edges from a target control image. IP-Adapter Plus uses one or more "
            "reference images to guide appearance. The current profiles cannot combine both "
            "controls in one Job."
        ),
        example="help job submit controlnet-canny",
        details=(
            "For target structure or pose represented by visible edges:\n"
            "  image help job submit controlnet-canny\n"
            "For subject appearance, clothing, or style references:\n"
            "  image help job submit ip-adapter-plus\n"
            "For request rejection, missing access, or invalid artifacts:\n"
            "  image help job submit recovery"
        ),
    ),
    "job submit controlnet-canny": Guide(
        guidance=(
            "Run the registered Canny ControlNet profile with a source image and a separate "
            "control image. The control image must already depict the target edge structure; "
            "this profile does not derive a requested human pose from prose and does not "
            "guarantee subject identity."
        ),
        example="job submit --request controlnet-job.json",
        details=(
            "1. Upload both inputs and retain the returned artifact_id values:\n"
            "  image artifact upload person.png --kind image --namespace guided-edit\n"
            "  image artifact upload bowing-control.png --kind image --namespace guided-edit\n"
            "2. Save this as controlnet-job.json after replacing both artifact IDs and the UUID:\n"
            "{\n"
            '  "request_id": "00000000-0000-4000-8000-000000000001",\n'
            '  "pipeline": {\n'
            '    "inputs": {\n'
            '      "image": {"artifact_id": "art_SOURCE_REPLACE_ME"},\n'
            '      "control": {"artifact_id": "art_CONTROL_REPLACE_ME"}\n'
            "    },\n"
            '    "steps": [{\n'
            '      "id": "edit",\n'
            '      "op": "edit",\n'
            '      "inputs": {\n'
            '        "image": {"artifact_id": "art_SOURCE_REPLACE_ME"},\n'
            '        "control": {"artifact_id": "art_CONTROL_REPLACE_ME"}\n'
            "      },\n"
            '      "params": {\n'
            '        "profile": "i2i-controlnet-canny-sd15",\n'
            '        "prompt": "the same person bowing politely",\n'
            '        "negative_prompt": null,\n'
            '        "strength": "0.75",\n'
            '        "guidance_scale": "7.5",\n'
            '        "inference_steps": 25,\n'
            '        "seed": 7,\n'
            '        "width": null,\n'
            '        "height": null,\n'
            '        "control_scale": "0.8",\n'
            '        "control_start": "0",\n'
            '        "control_end": "1"\n'
            "      }\n"
            "    }],\n"
            '    "outputs": [{"step_id": "edit", "output": "image"}]\n'
            "  },\n"
            '  "policy": {\n'
            '    "max_cost_usd": "0.25",\n'
            '    "deadline_seconds": 300,\n'
            '    "result_mode": "atomic"\n'
            "  }\n"
            "}\n"
            "3. Submit and inspect the returned Job ID:\n"
            "  image job submit --request controlnet-job.json\n"
            "  image job show JOB_ID"
        ),
    ),
    "job submit ip-adapter-plus": Guide(
        guidance=(
            "Run the registered IP-Adapter Plus profile when reference appearance matters. "
            "Supply a source image plus one or more reference images. This profile does not "
            "provide explicit pose control and cannot be combined with Canny ControlNet in "
            "the current public Job shape."
        ),
        example="job submit --request ip-adapter-job.json",
        details=(
            "1. Upload the source and one to four reference images and retain their artifact IDs.\n"
            "2. Save this as ip-adapter-job.json after replacing the IDs and UUID:\n"
            "{\n"
            '  "request_id": "00000000-0000-4000-8000-000000000001",\n'
            '  "pipeline": {\n'
            '    "inputs": {\n'
            '      "image": {"artifact_id": "art_SOURCE_REPLACE_ME"},\n'
            '      "reference_1": {"artifact_id": "art_REFERENCE_REPLACE_ME"}\n'
            "    },\n"
            '    "steps": [{\n'
            '      "id": "edit",\n'
            '      "op": "edit",\n'
            '      "inputs": {\n'
            '        "image": {"artifact_id": "art_SOURCE_REPLACE_ME"},\n'
            '        "reference_1": {"artifact_id": "art_REFERENCE_REPLACE_ME"}\n'
            "      },\n"
            '      "params": {\n'
            '        "profile": "i2i-ip-adapter-plus-sd15",\n'
            '        "prompt": "the same person bowing politely",\n'
            '        "negative_prompt": null,\n'
            '        "strength": "0.75",\n'
            '        "guidance_scale": "7.5",\n'
            '        "inference_steps": 25,\n'
            '        "seed": 7,\n'
            '        "width": null,\n'
            '        "height": null,\n'
            '        "reference_count": 1,\n'
            '        "reference_scale": "0.6"\n'
            "      }\n"
            "    }],\n"
            '    "outputs": [{"step_id": "edit", "output": "image"}]\n'
            "  },\n"
            '  "policy": {\n'
            '    "max_cost_usd": "0.25",\n'
            '    "deadline_seconds": 300,\n'
            '    "result_mode": "atomic"\n'
            "  }\n"
            "}\n"
            "For more references, add contiguous reference_2 through reference_4 entries to "
            "both input maps and set reference_count to the same total. reference_scale accepts "
            "0.1 through 1.\n"
            "3. Submit and inspect the returned Job ID:\n"
            "  image job submit --request ip-adapter-job.json\n"
            "  image job show JOB_ID"
        ),
    ),
    "job submit recovery": Guide(
        guidance="Recover from local request, authorization, artifact, policy, and dispatch errors. For model-specific settings use image model-profiles --details.",
        example="help job submit guided-edit",
        details=(
            "could not read JSON request: validate that --request names a readable UTF-8 JSON object.\n"
            "insufficient_scope: run image auth login with jobs:submit and the artifact scopes "
            "needed by the workflow.\n"
            "artifact_unavailable: confirm every artifact ID with image artifact show ARTIFACT_ID.\n"
            "image_edit_not_permitted: the authenticated principal is not allowlisted for durable "
            "image editing; this requires server-side configuration.\n"
            "job_policy_rejected: compare the request with the exact profile guide; registered "
            "guided edits require one step, exact inputs and parameters, one image output, and "
            "atomic result mode.\n"
            "job_dispatch_unavailable: retry only after the server Retry-After interval. Reuse the "
            "same request file so request_id preserves idempotency."
        ),
    ),
    "artifact upload recovery": Guide(
        guidance="Recover an Artifact upload before submitting a guided image Job.",
        example="artifact upload scene.png --kind image --namespace guided-edit",
        details=(
            "Confirm the file exists and is a supported image, renew authentication with "
            "artifacts:write when scope is missing, and rerun the upload once. If upload "
            "completion is ambiguous, inspect the returned artifact ID before creating a "
            "replacement. Continue with image help job submit guided-edit."
        ),
    ),
}


PROFILE_TOPICS = {
    "generate": "generation-standard",
    "prompt optimize": "prompt-optimizer-qwen2.5-3b",
    "caption": "vision-caption-standard",
    "edit image-to-image": "i2i-stable-diffusion-v1-5",
    "edit inpaint": "inpaint-stable-diffusion-v1-5",
    "edit segment": "segment-grounding-dino-sam2-tiny",
    "edit matte-portrait": "portrait-matting-birefnet-v1",
    "edit upscale": "upscale-realesrgan-x4plus",
    "edit restore": "upscale-realesrgan-x4plus",
    "search": "embedding-multimodal-siglip2",
    "job submit controlnet-canny": "i2i-controlnet-canny-sd15",
    "job submit ip-adapter-plus": "i2i-ip-adapter-plus-sd15",
}


def children(command: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return {
        name: child
        for action in command._actions
        if isinstance(action, argparse._SubParsersAction)
        for name, child in action.choices.items()
    }


def guide_children(key: str) -> tuple[str, ...]:
    prefix = f"{key} " if key else ""
    return tuple(
        sorted(
            {
                candidate.removeprefix(prefix).split(" ", 1)[0]
                for candidate in GUIDES
                if candidate.startswith(prefix) and candidate != key
            }
        )
    )


def show_help(root: argparse.ArgumentParser, topic: Sequence[str]) -> int:
    selected = root
    selected_depth = 0
    for index, name in enumerate(topic):
        available = children(selected)
        if name not in available:
            requested_key = " ".join(topic).replace("edit i2i", "edit image-to-image", 1)
            if requested_key in GUIDES:
                break
            current_key = " ".join(topic[:index]).replace("edit i2i", "edit image-to-image", 1)
            navigable = tuple(sorted(set(available) | set(guide_children(current_key))))
            print(
                f"error: unknown help topic {' '.join(topic[: index + 1])}; "
                f"available: {', '.join(navigable) or 'none'}",
                file=sys.stderr,
            )
            return 2
        selected = available[name]
        selected_depth = index + 1
    key = " ".join(topic).replace("edit i2i", "edit image-to-image", 1)
    guide = GUIDES.get(key)
    guidance, example = (
        (guide.guidance, guide.example)
        if guide is not None
        else TOPICS.get(key, ("Inspect the available options.", f"help {key}"))
    )
    heading = selected.format_help().rstrip()
    if selected_depth < len(topic):
        heading = f"usage: image help {key}\n\nHelp topic: {key}"
    sections = [
        heading,
        f"GUIDANCE\n{guidance}",
        "EXAMPLES (replace paths and IDs as needed)\n  image " + example,
    ]
    if guide is not None:
        sections.append("DETAILS\n" + guide.details)
    if key in PROFILE_TOPICS:
        sections.append(
            "SERVER GUIDANCE (requires authentication)\n  image model-profiles --profile "
            + PROFILE_TOPICS[key]
            + " --details\n"
            "Examples above illustrate syntax. Read current server guidance before choosing settings."
        )
    entries = children(selected) if selected_depth == len(topic) else {}
    navigable = tuple(sorted(set(entries) | set(guide_children(key))))
    if navigable:
        sections.append(
            "TOPICS\n" + "\n".join(f"  image help {' '.join((*topic, name))}" for name in navigable)
        )
    if topic:
        sections.append("RELATED\n  " + " ".join(("image", "help", *topic[:-1])))
    print("\n\n".join(sections))
    return 0
