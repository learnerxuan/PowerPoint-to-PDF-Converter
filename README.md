# PowerPoint to PDF Converter

A Python script that batch converts PowerPoint presentations (.pptx) to PDF documents using Microsoft PowerPoint's COM interface.

## Overview

This script automates the process of converting multiple PowerPoint files to PDF format in one go. It's particularly useful when you have a large number of presentations that need to be converted to PDF for sharing or archiving purposes.

## How It Works

The script leverages Python's COM (Component Object Model) interface to interact directly with Microsoft PowerPoint:

1. **Scans for PowerPoint files**: Searches the specified folder for all `.pptx` files
2. **Opens presentations**: Uses the installed PowerPoint application to open each presentation
3. **Converts to PDF**: Saves each presentation as a PDF file using PowerPoint's native export functionality
4. **Organizes output**: Creates a `Converted_PDFs` subfolder to keep the generated PDFs organized
5. **Cleanup**: Closes PowerPoint application after all conversions are complete

## Prerequisites

- **Windows OS**: This script only works on Windows due to COM interface requirements
- **Microsoft PowerPoint**: Must be installed and properly licensed
- **Python 3.x**: With `pywin32` package

## Installation

1. **Install required package**:
   ```bash
   pip install pywin32
   ```

2. **Download the script**:
   Clone this repository or download the `pptx_to_pdf_converter.py` file directly.

## Usage

1. **Configure the folder path**:
   Open `pptx_to_pdf_converter.py` and modify the `powerpoint_folder` variable:
   ```python
   powerpoint_folder = r"C:\path\to\your\powerpoint\files"
   ```

2. **Run the script**:
   ```bash
   python pptx_to_pdf_converter.py
   ```

3. **Check results**:
   - Converted PDFs will be saved in a new `Converted_PDFs` folder
   - Conversion progress and summary will be displayed in the console

## Code

```python
import os
import win32com.client as com
import time

def convert_pptx_to_pdf(input_folder):
    """
    Converts all PowerPoint files (.pptx) in a given folder to PDF files.
    """
    if not os.path.isdir(input_folder):
        print(f"Error: The folder '{input_folder}' does not exist.")
        return

    output_folder = os.path.join(input_folder, "Converted_PDFs")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output folder: '{output_folder}'")

    print(f"Starting conversion in folder: '{input_folder}'")

    powerpoint = None
    try:
        powerpoint = com.Dispatch("Powerpoint.Application")
        # Setting Visible to True for better diagnosis, but can be False for background conversion
        powerpoint.Visible = True # Set to False if you don't want PowerPoint window to appear
        print("Successfully connected to PowerPoint application.")
        time.sleep(1)
    except Exception as e:
        print(
            f"Error: Could not connect to PowerPoint application. Make sure PowerPoint is installed and not running with conflicting privileges.")
        print(f"Details: {e}")
        if powerpoint:
            try:
                powerpoint.Quit()
            except:
                pass
        return

    ppSaveAsPDF = 32 # Constant for PDF format

    converted_count = 0
    failed_count = 0

    for filename in os.listdir(input_folder):
        if filename.endswith(".pptx"):
            pptx_path = os.path.join(input_folder, filename)
            pdf_filename = os.path.splitext(filename)[0] + ".pdf"
            pdf_path = os.path.join(output_folder, pdf_filename)

            try:
                print(f"Converting '{filename}' to PDF...")
                # Open the presentation (WithWindow=False keeps presentation window hidden even if app is visible)
                presentation = powerpoint.Presentations.Open(pptx_path, WithWindow=False)
                presentation.SaveAs(pdf_path, ppSaveAsPDF)
                presentation.Close()
                print(f"Successfully converted '{filename}' to '{pdf_filename}'")
                converted_count += 1
            except Exception as e:
                print(f"Error converting '{filename}': {e}")
                failed_count += 1
                try:
                    if 'presentation' in locals() and not presentation.Saved:
                        presentation.Close()
                except:
                    pass

    if powerpoint:
        powerpoint.Quit()

    print("\nConversion Summary:")
    print(f"Total PowerPoint files found: {converted_count + failed_count}")
    print(f"Successfully converted: {converted_count}")
    print(f"Failed conversions: {failed_count}")
    print(f"PDFs are saved in: '{output_folder}'")


if __name__ == "__main__":
    # >>> IMPORTANT: CHANGE THIS PATH TO YOUR POWERPOINT FOLDER <<<
    powerpoint_folder = r"C:\Users\User\OneDrive - Asia Pacific University of Technology And Innovation (APU)\Desktop\APU\Data Analysis"
    
    convert_pptx_to_pdf(powerpoint_folder)
```

## Features

- **Batch processing**: Converts multiple PowerPoint files in one execution
- **Organized output**: Creates a dedicated folder for converted PDFs
- **Error handling**: Continues processing even if individual files fail to convert
- **Progress tracking**: Displays real-time conversion status and final summary
- **Flexible visibility**: Option to run PowerPoint in visible or background mode

## Configuration Options

You can customize the script behavior by modifying these settings:

- **PowerPoint visibility**: Set `powerpoint.Visible = False` to run conversions in the background
- **Output folder name**: Change `"Converted_PDFs"` to your preferred folder name
- **File extensions**: Modify the script to handle other PowerPoint formats (`.ppt`, `.pptm`)

## Troubleshooting

### Common Issues:

1. **"Could not connect to PowerPoint application"**
   - Ensure Microsoft PowerPoint is installed
   - Close any existing PowerPoint instances
   - Run the script as administrator if needed

2. **Permission errors**
   - Check that you have read access to the source folder
   - Ensure write permissions for the output directory
   - Verify PowerPoint files are not currently open

3. **Module not found error**
   - Install pywin32: `pip install pywin32`
   - Restart your terminal/command prompt after installation

## Limitations

- Windows-only due to COM interface dependency
- Requires Microsoft PowerPoint installation
- Cannot convert password-protected presentations without manual intervention
- Processing speed depends on presentation complexity and system performance

## License

This project is open source and available under the [MIT License](LICENSE).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue for any bugs or feature requests.

## Acknowledgments

- Uses the `pywin32` library for COM interface access
- Built on Microsoft PowerPoint's native export capabilities
