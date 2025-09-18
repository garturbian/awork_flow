import sys
import re
import html
from googletrans import Translator

def translate_srt(input_file, output_file, dest_lang='zh-tw'):
    """
    Translate an SRT file to the specified language.
    
    Args:
        input_file (str): Path to the input SRT file
        output_file (str): Path to the output translated SRT file
        dest_lang (str): Destination language code (default: 'zh-tw' for Traditional Chinese)
    """
    translator = Translator()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split the SRT file into blocks
    blocks = re.split(r'\n\s*\n', content.strip())
    
    translated_blocks = []
    
    for i, block in enumerate(blocks, 1):
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # First line is the subtitle number
            subtitle_number = lines[0]
            # Second line is the time code
            time_code = lines[1]
            # The rest are the subtitle text (may be multiple lines)
            subtitle_text = '\n'.join(lines[2:])
            
            # Translate the subtitle text
            try:
                translated = translator.translate(subtitle_text, dest=dest_lang)
                translated_text = translated.text
                
                # Remove HTML tags from translated text
                translated_text = re.sub(r'<[^>]+>', '', translated_text)
                # Remove ASS/SSA style tags like {\an5}
                translated_text = re.sub(r'{\\[^}]*}', '', translated_text)
                # Unescape HTML entities
                translated_text = html.unescape(translated_text)
                # Remove extra whitespace
                translated_text = translated_text.strip()
                
                # Create the translated block
                translated_block = f"{subtitle_number}\n{time_code}\n{translated_text}"
                translated_blocks.append(translated_block)
                
                print(f"Translated subtitle {i}")
            except Exception as e:
                print(f"Error translating subtitle {i}: {e}")
                # Keep the original text if translation fails
                translated_block = f"{subtitle_number}\n{time_code}\n{subtitle_text}"
                translated_blocks.append(translated_block)
        else:
            # Keep the block as is if it doesn't match the expected format
            translated_blocks.append(block)
    
    # Write the translated content to the output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(translated_blocks) + '\n\n')
    
    print(f"Translation complete. Output saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python translate_srt.py <input_file.srt> [output_file.srt]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        # Default output file name: insert _zh-tw before .srt extension
        output_file = input_file.replace('.srt', '_zh-tw.srt')
    
    translate_srt(input_file, output_file)