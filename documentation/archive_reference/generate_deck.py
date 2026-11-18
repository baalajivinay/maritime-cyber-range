#!/usr/bin/env python3
"""
Generate an updated, streamlined presentation addressing all feedback:
- Title: "What is a Cyber-Physical Testbed?"
- Concise, short bullet points only (no over-explaining).
- Cleanly crop/round all images via Pillow with smooth anti-aliased corners so
  rectangular images fit cleanly without overlapping boundaries.
- Remove pictures on Slide 7 (Attacks Implemented & Observed Impact).
- Focus purely on current standing: architecture, vehicle twins, and working model screenshots.
- Plain simple English generic to the autonomous robotics / maritime domain.
- Export to high-quality PDF via LibreOffice headless.
"""
import os
import sys
from PIL import Image, ImageDraw
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

REPO = "/home/vinay/maritime-cyber-range"
EVIDENCE = os.path.join(REPO, "evidence")
SCREENSHOTS = os.path.join(EVIDENCE, "screenshots")
DEMO = os.path.join(EVIDENCE, "demo_captures")
ROUNDED_DIR = "/tmp/rounded_mcr_images"
os.makedirs(ROUNDED_DIR, exist_ok=True)

PPTX_OUT = os.path.join(EVIDENCE, "Maritime_Cyber_Range_Architecture_and_Walkthrough.pptx")
PDF_OUT = os.path.join(EVIDENCE, "Maritime_Cyber_Range_Architecture_and_Walkthrough.pdf")

# Palette: Clean Naval Slate Theme
BG_COLOR = RGBColor(11, 19, 43)        # #0B132B Dark Navy
CARD_BG = RGBColor(24, 32, 54)         # #182036 Slate Card
CARD_BORDER = RGBColor(56, 75, 102)    # #384B66 Border
ACCENT_CYAN = RGBColor(0, 180, 216)    # #00B4D8 Tech Cyan
ACCENT_GREEN = RGBColor(56, 176, 0)    # #38B000 Success Green
ACCENT_RED = RGBColor(230, 57, 70)     # #E63946 Alert Red
TEXT_WHITE = RGBColor(248, 249, 250)   # #F8F9FA Clean White
TEXT_MUTED = RGBColor(156, 175, 196)   # #9CAFC4 Muted Subtitle
ACCENT_GOLD = RGBColor(255, 183, 3)    # #FFB703 Gold

def round_and_crop_image(img_path, out_name, radius=24, aspect_ratio=None):
    """Cleanly crops and rounds image corners using Pillow anti-aliasing."""
    im = Image.open(img_path).convert('RGBA')
    w, h = im.size
    
    if aspect_ratio:
        # Center crop to target aspect ratio
        target_w, target_h = aspect_ratio
        current_ar = w / h
        target_ar = target_w / target_h
        if current_ar > target_ar:
            new_w = int(h * target_ar)
            offset = (w - new_w) // 2
            im = im.crop((offset, 0, offset + new_w, h))
        else:
            new_h = int(w / target_ar)
            offset = (h - new_h) // 2
            im = im.crop((0, offset, w, offset + new_h))
        w, h = im.size

    # Supersample mask 4x for smooth rounded edges
    scale = 4
    mask = Image.new('L', (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w * scale, h * scale)], radius=radius * scale, fill=255)
    mask = mask.resize((w, h), Image.Resampling.LANCZOS)

    # Paste with mask
    rounded = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    rounded.paste(im, (0, 0), mask=mask)
    out_path = os.path.join(ROUNDED_DIR, out_name)
    rounded.save(out_path, 'PNG')
    return out_path

# Process images with matching corner radius
IMG_ARCH = round_and_crop_image(os.path.join(SCREENSHOTS, "system_architecture_diagram.png"), "arch_round.png", radius=18)
IMG_MENU = round_and_crop_image(os.path.join(SCREENSHOTS, "godot_window_clean.png"), "menu_round.png", radius=18, aspect_ratio=(16, 10))
IMG_USV_INT = round_and_crop_image(os.path.join(SCREENSHOTS, "godot_3d_interceptor_usv.png"), "usv_int_round.png", radius=18, aspect_ratio=(16, 10))
IMG_USV_SURV = round_and_crop_image(os.path.join(SCREENSHOTS, "godot_3d_survey_usv.png"), "usv_surv_round.png", radius=18, aspect_ratio=(16, 10))
IMG_AUV_MAYA = round_and_crop_image(os.path.join(SCREENSHOTS, "godot_3d_maya_auv.png"), "auv_maya_round.png", radius=18, aspect_ratio=(16, 10))
IMG_AUV_150 = round_and_crop_image(os.path.join(SCREENSHOTS, "godot_3d_auv150.png"), "auv_150_round.png", radius=18, aspect_ratio=(16, 10))
IMG_DASH = round_and_crop_image(os.path.join(SCREENSHOTS, "dashboard_screenshot.png"), "dash_round.png", radius=18)

def create_presentation():
    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs

def set_slide_background(slide):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR

def add_header(slide, title, category="AUTONOMOUS MARITIME CYBER-PHYSICAL TESTBED"):
    # Category tag
    tb_c = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.3))
    p_c = tb_c.text_frame.paragraphs[0]
    p_c.text = category.upper()
    p_c.font.size = Pt(10)
    p_c.font.bold = True
    p_c.font.color.rgb = ACCENT_CYAN

    # Title
    tb_t = slide.shapes.add_textbox(Inches(0.8), Inches(0.65), Inches(11.7), Inches(0.6))
    p_t = tb_t.text_frame.paragraphs[0]
    p_t.text = title
    p_t.font.size = Pt(22)
    p_t.font.bold = True
    p_t.font.color.rgb = TEXT_WHITE

    # Underline
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.3), Inches(11.733), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = CARD_BORDER
    line.line.color.rgb = CARD_BORDER

def add_card(slide, left, top, width, height, bg_color=CARD_BG, border_color=CARD_BORDER):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    shape.line.color.rgb = border_color
    shape.line.width = Pt(1.2)
    return shape

# ----------------- SLIDE 1: Title Slide -----------------
def build_slide_1(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)

    # Top accent bar
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.08))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = ACCENT_CYAN
    top_bar.line.color.rgb = ACCENT_CYAN

    # Center card
    add_card(slide, Inches(1.0), Inches(1.1), Inches(11.333), Inches(5.3))

    tb = slide.shapes.add_textbox(Inches(1.4), Inches(1.4), Inches(10.533), Inches(2.2))
    tf = tb.text_frame
    tf.word_wrap = True

    p0 = tf.paragraphs[0]
    p0.text = "What is a Cyber-Physical Testbed?"
    p0.font.size = Pt(30)
    p0.font.bold = True
    p0.font.color.rgb = TEXT_WHITE
    p0.alignment = PP_ALIGN.CENTER

    p1 = tf.add_paragraph()
    p1.text = "Architecture & Implementation for Autonomous Maritime Vessels (USVs & AUVs)"
    p1.font.size = Pt(16)
    p1.font.bold = True
    p1.font.color.rgb = ACCENT_CYAN
    p1.alignment = PP_ALIGN.CENTER
    p1.space_before = Pt(8)

    p2 = tf.add_paragraph()
    p2.text = "Vinaybaalaji PNS (CB.SC.U4CYS24061)   •   Sanjai S (CB.SC.U4CYS24051)"
    p2.font.size = Pt(13)
    p2.font.color.rgb = TEXT_WHITE
    p2.alignment = PP_ALIGN.CENTER
    p2.space_before = Pt(10)

    p3 = tf.add_paragraph()
    p3.text = "3rd Year, B.Tech Cybersecurity   |   Software-in-the-Loop Implementation Status"
    p3.font.size = Pt(11)
    p3.font.color.rgb = TEXT_MUTED
    p3.alignment = PP_ALIGN.CENTER
    p3.space_before = Pt(4)

    # 3 Summary Cards
    cards_data = [
        ("THE CYBER LAYER", "Real Autopilot Firmware", "Executes production ArduPilot / ArduSub binaries, 24-state EKF3 sensor fusion, and real MAVLink 2 telemetry."),
        ("THE PHYSICAL LAYER", "Multi-Engine Hydrodynamics", "Simulates water drag, 6-DOF added mass, buoyancy, and ocean currents using Gazebo Sim and Stonefish."),
        ("THE ATTACK LAYER", "Adversarial Injection Suite", "Direct injection of GNSS coordinate shifts, AIS ghost vessels, acoustic telemetry noise, and C2 overrides.")
    ]
    card_w = Inches(3.2)
    card_h = Inches(1.8)
    for i, (title, sub, desc) in enumerate(cards_data):
        x = Inches(1.5 + i * 3.6)
        y = Inches(4.2)
        add_card(slide, x, y, card_w, card_h, bg_color=BG_COLOR, border_color=CARD_BORDER)
        tb_c = slide.shapes.add_textbox(x + Inches(0.15), y + Inches(0.15), card_w - Inches(0.3), card_h - Inches(0.3))
        tf_c = tb_c.text_frame
        tf_c.word_wrap = True
        
        pt = tf_c.paragraphs[0]
        pt.text = title
        pt.font.size = Pt(11)
        pt.font.bold = True
        pt.font.color.rgb = ACCENT_GOLD
        
        ps = tf_c.add_paragraph()
        ps.text = sub
        ps.font.size = Pt(11)
        ps.font.bold = True
        ps.font.color.rgb = TEXT_WHITE
        ps.space_before = Pt(2)

        pd = tf_c.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(9.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(4)

# ----------------- SLIDE 2: What is a Cyber-Physical Testbed? -----------------
def build_slide_2(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Understanding Cyber-Physical Testbeds: Concept & Scope", "1. TESTBED DEFINITION")

    # Left: Definition & Working Mechanism
    add_card(slide, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.3))
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(5.2), Inches(4.8))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True

    p = tf_l.paragraphs[0]
    p.text = "What is a Cyber-Physical Testbed?"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN

    points_l = [
        ("Bridging Cyber and Physical Worlds", "A testbed that directly links real autonomous decision software ('Cyber') with realistic environmental physics ('Physical') in a closed feedback loop."),
        ("Closed-Loop Feedback", "Physics engines calculate vessel motion -> feed simulated sensors to autopilot -> autopilot computes thruster/rudder commands -> physics engine applies resulting forces."),
        ("Why Real Software Matters", "Instead of high-level math approximations, the testbed executes the exact firmware running on actual vessel hardware (ArduPilot/ArduSub SITL).")
    ]
    for title, desc in points_l:
        pt = tf_l.add_paragraph()
        pt.text = "• " + title
        pt.font.size = Pt(12)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(12)
        pd = tf_l.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(10.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

    # Right: Why Software-in-the-Loop Pre-Sea Testing is Essential
    add_card(slide, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.3))
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(1.8), Inches(5.3), Inches(4.8))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True

    p_r = tf_r.paragraphs[0]
    p_r.text = "Why It is Needed for Autonomous Vessels"
    p_r.font.size = Pt(16)
    p_r.font.bold = True
    p_r.font.color.rgb = ACCENT_GOLD

    points_r = [
        ("No Human Eyes on the Bridge", "Manned ships have navigators to visually spot GPS errors. Autonomous vessels rely 100% on wireless sensor feeds—if corrupted, the craft turns blindly."),
        ("Sea Trials Prohibited for Cyber Attacks", "Transmitting live GPS spoofing or radio jamming in open ocean violates maritime radio laws (SOLAS/ITU) and risks fatal collisions or vessel loss."),
        ("High Cost of Open Water Testing", "Chartering naval support vessels and chase boats costs $30,000 to $100,000 per sea day. Software testbeds allow unlimited, zero-cost, repeatable testing."),
        ("Safety & Repeatability", "Engineers can safely test extreme edge cases, deliberate attacks, and failsafe recoveries without endangering physical hulls.")
    ]
    for title, desc in points_r:
        pt = tf_r.add_paragraph()
        pt.text = "• " + title
        pt.font.size = Pt(12)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(10)
        pd = tf_r.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(10.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

# ----------------- SLIDE 3: System Architecture -----------------
def build_slide_3(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "System Architecture: End-to-End Simulation Pipeline", "2. ARCHITECTURE & WORKFLOW")

    # Architecture Image (with pre-rounded clean corners)
    slide.shapes.add_picture(IMG_ARCH, Inches(0.8), Inches(1.6), width=Inches(8.2), height=Inches(5.3))

    # Right Summary Column
    add_card(slide, Inches(9.2), Inches(1.6), Inches(3.3), Inches(5.3))
    tb = slide.shapes.add_textbox(Inches(9.4), Inches(1.8), Inches(2.9), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Architecture Summary"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN

    points = [
        ("Operator Layer", "Godot 4 Vulkan 3D front-end for visual tracking + Web GCS Leaflet radar map."),
        ("Fast UDP Bridge", "Non-blocking JSON bus (:14650 telemetry, :14651 command) for low-latency sync."),
        ("Attack Engine", "Modular injection of GNSS drift, AIS ghost vessels, acoustic noise, and C2 overrides."),
        ("Autopilot Core", "Live ArduPilot / ArduSub SITL binary executing 24-state EKF3 sensor fusion."),
        ("Dual-Physics", "Gazebo Sim (DART solver) for surface craft; Stonefish (6-DOF hydrodynamics) for AUVs.")
    ]
    for title, desc in points:
        pt = tf.add_paragraph()
        pt.text = "• " + title
        pt.font.size = Pt(11)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(8)
        pd = tf.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(9.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

# ----------------- SLIDE 4: Surface USV Digital Twins -----------------
def build_slide_4(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Working Model: Surface Digital Twins (USV)", "3. VEHICLE TWINS (SURFACE)")

    # Left: Mission Setup Menu
    slide.shapes.add_picture(IMG_MENU, Inches(0.8), Inches(1.6), width=Inches(5.6), height=Inches(3.4))

    # Right: Fast Interceptor USV
    slide.shapes.add_picture(IMG_USV_INT, Inches(6.8), Inches(1.6), width=Inches(5.7), height=Inches(3.4))

    # Bottom Left Card: Harbor Sites
    add_card(slide, Inches(0.8), Inches(5.2), Inches(5.6), Inches(1.7))
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(5.3), Inches(5.2), Inches(1.4))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p_l = tf_l.paragraphs[0]
    p_l.text = "Calibrated Test Harbor Sites"
    p_l.font.size = Pt(12)
    p_l.font.bold = True
    p_l.font.color.rgb = ACCENT_CYAN

    p_l2 = tf_l.add_paragraph()
    p_l2.text = "• Kochi: Littoral naval harbor channels and shallow-water multipath.\n• Mumbai: High-density shipping lanes and commercial AIS corridors.\n• Visakhapatnam: Deep-water approaches and naval maneuvering basins."
    p_l2.font.size = Pt(10)
    p_l2.font.color.rgb = TEXT_WHITE
    p_l2.space_before = Pt(4)

    # Bottom Right Card: Surface Twins
    add_card(slide, Inches(6.8), Inches(5.2), Inches(5.7), Inches(1.7))
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(5.3), Inches(5.3), Inches(1.4))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p_r = tf_r.paragraphs[0]
    p_r.text = "Surface Platform Characteristics"
    p_r.font.size = Pt(12)
    p_r.font.bold = True
    p_r.font.color.rgb = ACCENT_GREEN

    p_r2 = tf_r.add_paragraph()
    p_r2.text = "• Fast Interceptor USV: Planing hull, dual thrusters, rapid reaction patrol.\n• Coastal Survey USV: Twin-demihull catamaran with high stability for survey.\n• Physics Engine: Gazebo Sim + DART solver modeling water drag and waves."
    p_r2.font.size = Pt(10)
    p_r2.font.color.rgb = TEXT_WHITE
    p_r2.space_before = Pt(4)

# ----------------- SLIDE 5: Subsurface AUV Digital Twins -----------------
def build_slide_5(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Working Model: Subsurface Digital Twins (AUV)", "4. VEHICLE TWINS (UNDERWATER)")

    # Left: Maya AUV
    slide.shapes.add_picture(IMG_AUV_MAYA, Inches(0.8), Inches(1.6), width=Inches(5.6), height=Inches(3.4))

    # Right: AUV-150
    slide.shapes.add_picture(IMG_AUV_150, Inches(6.8), Inches(1.6), width=Inches(5.7), height=Inches(3.4))

    # Bottom Left Card: Hydrodynamic Modeling
    add_card(slide, Inches(0.8), Inches(5.2), Inches(5.6), Inches(1.7))
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(5.3), Inches(5.2), Inches(1.4))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p_l = tf_l.paragraphs[0]
    p_l.text = "Stonefish Hydrodynamic Simulation"
    p_l.font.size = Pt(12)
    p_l.font.bold = True
    p_l.font.color.rgb = ACCENT_CYAN

    p_l2 = tf_l.add_paragraph()
    p_l2.text = "• 6-DOF Hydrodynamic Model: Added mass, linear/quadratic damping, restoring forces.\n• Ballast & Buoyancy: Realistic submersion, pitch/trim moments, and thruster coupling.\n• Dedicated C++ Physics: Solves underwater dynamics cleanly and pipes states to Godot."
    p_l2.font.size = Pt(10)
    p_l2.font.color.rgb = TEXT_WHITE
    p_l2.space_before = Pt(4)

    # Bottom Right Card: Subsea AUVs
    add_card(slide, Inches(6.8), Inches(5.2), Inches(5.7), Inches(1.7))
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(5.3), Inches(5.3), Inches(1.4))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p_r = tf_r.paragraphs[0]
    p_r.text = "Subsurface Twins & Telemetry"
    p_r.font.size = Pt(12)
    p_r.font.bold = True
    p_r.font.color.rgb = ACCENT_GOLD

    p_r2 = tf_r.add_paragraph()
    p_r2.text = "• Maya AUV: Torpedo-class autonomous submersible with 3D path following.\n• AUV-150: Deep-rated survey submersible under closed-loop ArduSub depth hold.\n• Acoustic Telemetry: Simulates underwater latency (1500 m/s sound speed) & USBL."
    p_r2.font.size = Pt(10)
    p_r2.font.color.rgb = TEXT_WHITE
    p_r2.space_before = Pt(4)

# ----------------- SLIDE 6: Tactical GCS Interface -----------------
def build_slide_6(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Working Model: Tactical Command & Control (GCS) Console", "5. CONTROL INTERFACE")

    # Dashboard screenshot with clean rounded corners
    slide.shapes.add_picture(IMG_DASH, Inches(0.8), Inches(1.6), width=Inches(7.8), height=Inches(5.3))

    # Right Features Column
    add_card(slide, Inches(8.8), Inches(1.6), Inches(3.7), Inches(5.3))
    tb = slide.shapes.add_textbox(Inches(9.0), Inches(1.8), Inches(3.3), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Console Capabilities"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = ACCENT_CYAN

    features = [
        ("Live Vehicle HUD", "Displays real-time MAVLink telemetry: Mode (MANUAL/GUIDED/AUTO), Speed (m/s), Heading, and Depth."),
        ("Position Integrity Monitor", "Compares simulated ground-truth position against the autopilot's internal Kalman filter belief. In nominal state: 'true = believed (0.0 m)'."),
        ("Interactive Attack Suite", "Enables one-click injection of GPS Spoofing, AIS Spoofing, C2 Throttle Overrides, and Acoustic disruption."),
        ("Interactive Radar & Waypoints", "Point-and-click waypoint navigation on an interactive tactical map with real-time route plotting."),
        ("Real-Time Anomaly Stream", "Instantly flags sensor divergence, packet drops, and failsafe trigger states.")
    ]
    for title, desc in features:
        pt = tf.add_paragraph()
        pt.text = "• " + title
        pt.font.size = Pt(11)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(8)
        pd = tf.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(9.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

# ----------------- SLIDE 7: Attacks Implemented & Impact (NO PICTURES) -----------------
def build_slide_7(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Current Standing: Attacks Implemented & Observed Impact", "6. EXPERIMENTAL FINDINGS")

    # 4 Structured Attack Cards (2x2 grid, NO PICTURES as requested)
    attacks = [
        ("1. GPS / GNSS Coordinate Spoofing", ACCENT_RED,
         "Attack Method:", "Injected forged NMEA / MAVLink GPS_RAW_INT coordinate streams. A gradual ramp drift was applied to bypass simple threshold checks.",
         "Observed Result:", "The 24-state EKF accepted the false drift as genuine motion, causing the vessel to deviate by 25.4 m to 49.9 m from its actual mission course while believing it was perfectly on track."),
        
        ("2. AIS Ghost Vessel & Identity Spoofing", ACCENT_CYAN,
         "Attack Method:", "Broadcast forged NMEA 0183 AIVDM packet structures over simulated VHF maritime frequencies.",
         "Observed Result:", "Successfully injected phantom collision targets into the tactical radar, forcing autonomous collision-avoidance algorithms to execute unnecessary emergency turns."),
        
        ("3. MAVLink C2 Command Takeover", ACCENT_GOLD,
         "Attack Method:", "Injected unauthorized high-frequency RC_CHANNELS_OVERRIDE and SET_MODE packets.",
         "Observed Result:", "Seized direct control of the rudder and throttle channels from the ground station, overriding operator guidance commands until attack termination."),
        
        ("4. Acoustic Telemetry Corruption", ACCENT_GREEN,
         "Attack Method:", "Spoofed underwater USBL acoustic positioning pulses and injected artificial transmission latency.",
         "Observed Result:", "Successfully deflected subsea AUV navigation paths in an environment where satellite navigation (GPS) is completely unavailable.")
    ]

    card_w = Inches(5.6)
    card_h = Inches(2.5)

    for i, (title, color, m_label, m_desc, r_label, r_desc) in enumerate(attacks):
        col = i % 2
        row = i // 2
        x = Inches(0.8 + col * 6.1)
        y = Inches(1.6 + row * 2.8)

        add_card(slide, x, y, card_w, card_h)
        tb = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(0.15), card_w - Inches(0.4), card_h - Inches(0.3))
        tf = tb.text_frame
        tf.word_wrap = True

        pt = tf.paragraphs[0]
        pt.text = title
        pt.font.size = Pt(13)
        pt.font.bold = True
        pt.font.color.rgb = color

        pm = tf.add_paragraph()
        pm.text = "• " + m_label + " " + m_desc
        pm.font.size = Pt(10)
        pm.font.color.rgb = TEXT_WHITE
        pm.space_before = Pt(6)

        pr = tf.add_paragraph()
        pr.text = "• " + r_label + " " + r_desc
        pr.font.size = Pt(10)
        pr.font.color.rgb = TEXT_MUTED
        pr.space_before = Pt(4)

# ----------------- SLIDE 8: Current Standing vs HITL Next Step -----------------
def build_slide_8(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide)
    add_header(slide, "Current Standing & Hardware-in-the-Loop (HITL) Roadmap", "7. STATUS & NEXT STEPS")

    # Left: What is Completed Now
    add_card(slide, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.3))
    tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(5.2), Inches(4.8))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True

    p_l = tf_l.paragraphs[0]
    p_l.text = "Current Standing: Software-in-the-Loop"
    p_l.font.size = Pt(16)
    p_l.font.bold = True
    p_l.font.color.rgb = ACCENT_GREEN

    completed = [
        ("Production Autopilot SITL", "ArduPilot and ArduSub binaries running with live 24-state EKF3 sensor fusion and hardware-identical state machines."),
        ("4 Vehicle Digital Twins", "Fully modeled Fast Interceptor USV, Coastal Survey USV, Maya AUV, and AUV-150 across surface and subsurface domains."),
        ("Dual-Physics Integration", "Gazebo Sim for surface USV hydrodynamic drag + Stonefish for underwater 6-DOF added mass and buoyancy."),
        ("3 Calibrated Test Harbors", "Operational geographical setups for Kochi, Mumbai, and Visakhapatnam."),
        ("4 Attack Vectors Validated", "Demonstrated and measured impact of GPS spoofing, AIS ghosting, MAVLink takeover, and acoustic noise.")
    ]
    for title, desc in completed:
        pt = tf_l.add_paragraph()
        pt.text = "✓ " + title
        pt.font.size = Pt(11)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(8)
        pd = tf_l.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(9.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

    # Right: Next Step - Hardware-in-the-Loop (from Research Proposal)
    add_card(slide, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.3))
    tb_r = slide.shapes.add_textbox(Inches(7.0), Inches(1.8), Inches(5.3), Inches(4.8))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True

    p_r = tf_r.paragraphs[0]
    p_r.text = "Next Step: Hardware-in-the-Loop (HITL)"
    p_r.font.size = Pt(16)
    p_r.font.bold = True
    p_r.font.color.rgb = ACCENT_GOLD

    hitl_steps = [
        ("Why HITL is Needed", "Software simulation models environmental conditions cleanly. Real embedded boards introduce hardware clock jitter, serial delays, and physical bus latency."),
        ("Embedded Flight Controllers", "Connecting physical autopilot boards (Pixhawk / Cube Orange) over UART/CAN bus while the physics engine runs on the workstation."),
        ("Software-Defined Radios (SDR)", "Transmitting over-the-air signals using HackRF / BladeRF in shielded RF enclosures to test actual radio reception."),
        ("Validation Benchmark", "Following validated methodologies (e.g. Kwon et al.) to establish a reliable, pre-sea cyber resilience verification framework.")
    ]
    for title, desc in hitl_steps:
        pt = tf_r.add_paragraph()
        pt.text = "• " + title
        pt.font.size = Pt(11)
        pt.font.bold = True
        pt.font.color.rgb = TEXT_WHITE
        pt.space_before = Pt(8)
        pd = tf_r.add_paragraph()
        pd.text = desc
        pd.font.size = Pt(9.5)
        pd.font.color.rgb = TEXT_MUTED
        pd.space_before = Pt(2)

def main():
    print("Building 8-slide presentation...")
    prs = create_presentation()
    build_slide_1(prs)
    build_slide_2(prs)
    build_slide_3(prs)
    build_slide_4(prs)
    build_slide_5(prs)
    build_slide_6(prs)
    build_slide_7(prs)
    build_slide_8(prs)

    prs.save(PPTX_OUT)
    print(f"PowerPoint successfully created: {PPTX_OUT} ({os.path.getsize(PPTX_OUT)} bytes)")

    # Convert to PDF using LibreOffice headless
    print("Exporting presentation to PDF via LibreOffice...")
    cmd = f"soffice --headless --convert-to pdf '{PPTX_OUT}' --outdir '{EVIDENCE}'"
    ret = os.system(cmd)
    if ret == 0 and os.path.exists(PDF_OUT):
        print(f"PDF successfully exported: {PDF_OUT} ({os.path.getsize(PDF_OUT)} bytes)")
    else:
        print(f"Failed to export PDF! Return code: {ret}")
        sys.exit(1)

    # Also copy to root home directory for convenience
    os.system(f"cp '{PDF_OUT}' /home/vinay/")
    os.system(f"cp '{PPTX_OUT}' /home/vinay/")
    print("Copied updated files to /home/vinay/")

if __name__ == "__main__":
    main()
