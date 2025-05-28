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
    powerpoint_folder = r"CHANGE THIS PATH TO YOUR POWERPOINT FOLDER"
    
    convert_pptx_to_pdf(powerpoint_folder)
