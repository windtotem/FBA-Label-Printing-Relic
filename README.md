Features

Auto-classification — scans PDF text and sorts files into four types
Smart merging — concatenates all files of the same type into one output PDF
Crop & rotate — UPS tracking pages and Small List pages can be cropped and rotated with configurable settings
Crop Calibrator — interactive tool to visually drag a crop box over a PDF page and apply the ratios directly, no code editing needed
Unclassified handling — any PDF that doesn't match a known type is collected into unclassified.pdf and flagged in the log, never silently dropped
Portable — can be packaged into a single .exe for use on any Windows 11 machine


File Types & Detection
Output FileDetected Bytracking_list.pdfText contains UPS, DPD, DHL, FedEx, or FEDEXasn.pdfText contains ASNean.pdfText contains EANsmall_list.pdfText contains hoverboard (case-insensitive)unclassified.pdfNo match found

UPS pages and Small List pages receive special crop and rotation treatment (see Calibration below).


Project Structure
pdf_processor.py   — main application
build.bat          — one-click build script (produces a standalone .exe)
README.md          — this file
dist/              — created after build, contains PDF_Auto_Processor.exe

Requirements (for running from source)

·Python 3.10 or higher
·Dependencies:
  pip install pypdf pymupdf pillow

Building a Standalone Executable (Windows)
  To create a single .exe you can copy to any Windows 11 machine:

Double-click build.bat
Wait for it to finish (it installs dependencies and runs PyInstaller automatically)
Find PDF_Auto_Processor.exe inside the dist\ folder
Copy just that .exe — no Python or libraries needed on the target machine


Note: The first launch of the .exe may take 5–15 seconds as it unpacks itself. This is normal behaviour for PyInstaller bundles. 
Some antivirus software may flag it — you can safely whitelist it.

Usage

  1.Launch the app (either python pdf_processor.py or the built .exe)
  2.Click Browse… and select the folder containing your PDF files
  3.Click ▶ Run Processing
  4.Output files are saved to a processed\ subfolder inside your selected folder

Crop Calibration
UPS and Small List PDFs have configurable crop areas. To set or adjust them:

  1.Click ✂ Crop Calibrator
  2.Click Open PDF… and select a sample file of the type you want to calibrate
  3.Navigate pages with ◀ ▶ if needed
  4.Drag a rectangle on the page image to define the area to keep
  5.Set the rotation angle if needed (0 / 90 / 180 / 270°)
  6.Select the target type (UPS tracking or Small List)
  7.Click Apply to config — settings take effect immediately for the current session

To make crop settings permanent across restarts, copy the ratio values shown in the calibrator status bar into the CROP_CONFIG block at the top of pdf_processor.py:
CROP_CONFIG = {
    "ups": {
        "enabled":  True,
        "left":     0.0,    # ← paste your values here
        "bottom":   0.05,
        "right":    1.0,
        "top":      0.95,
        "rotation": 90,
    },
    "small_list": {
        "enabled":  True,
        "left":     0.0,    # ← paste your values here
        "bottom":   0.0,
        "right":    1.0,
        "top":      1.0,
        "rotation": 0,
    },
}

Output
All output files are written to a processed\ subfolder inside the selected folder:
your-folder/
├── file1.pdf
├── file2.pdf
└── processed/
    ├── tracking_list.pdf
    ├── asn.pdf
    ├── ean.pdf
    ├── small_list.pdf
    └── unclassified.pdf   ← only created if unmatched files exist

Roadmap

 *Auto-download PDFs from source
 *Sort and match PDFs against data from a website
