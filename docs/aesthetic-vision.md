# Rusty Industrial HUD Aesthetic

## Overview
Algent's UI shifts from a high-tech neon rig to a **worn, utilitarian industrial control interface**. Think 80s analog computing meets a rusted space freighter. The interface feels "burned in" to an old CRT monitor—warm, dim, and tactile. It prioritizes function over flash, with a passive, cozy darkness that feels lived-in.

## Visual Pillars
- **Warm Darkness**: Deep, muddy browns, warm charcoals, and oil-slick blacks replace the cold purples. The background is a passive gradient of heat and shadow.
- **Rusty & Faded**: Accents are oxides—rust orange, burnt sienna, faded amber, and dried moss green. No electric cyans or magentas.
- **Analog Grid**: The "mesh" is a constant, tactile layer—a faint, warm grid that provides structure (snap points) but fades in and out like a ghost artifact or screen burn-in.
- **Utilitarian Type**: Monospace dominates. Text is dim (like a dying phosphor screen) unless active.
- **Passive Simplicity**: The UI doesn't scream for attention. It sits back, a tool waiting to be used. Simple shapes, minimal gradients on controls.

## Color Palette
| Role | Hex | Notes |
| --- | --- | --- |
| **Background** | `#0f0d0c` - `#1c1917` | Deep warm charcoal to oil black. |
| **Panel Base** | `#191512` | Slightly lighter warm dark for cards/panels. |
| **Primary Text** | `#d6d3d1` | Stone gray, not pure white. |
| **Accent (Active)** | `#fb923c` | Faded orange / amber. |
| **Accent (Alert)** | `#ef4444` | Muted red/rust. |
| **Accent (Steady)** | `#84cc16` | Old phosphor green (muted). |
| **Grid/Mesh** | `#292524` | Warm stone, very low opacity. |

## Layout & artifacts
- **Mesh Grid**: A background layer of fine lines or dots, simulating a physical mesh or screen matrix.
- **Burn-in / Vignette**: Edges of the screen should feel darker, focusing attention on the center.
- **Scanlines**: Subtle, slow-moving or static horizontal lines to sell the CRT vibe, but kept "dim" and non-intrusive.
- **Boxy & Rigid**: Borders are solid, 1px or 2px, often with a "cut" corner or exposed frame look.

## Typography
- **Primary**: Monospace (IBM Plex Mono, JetBrains Mono) for almost everything.
- **Labels**: Small, uppercase, tracked out.
- **Hierarchy**: distiguish by color brightness and weight, not just size.

## Motion
- **Sluggish/Analog**: Transitions are instant or have a slight "fade/decay" curve, like a light bulb turning off. No spring physics.
