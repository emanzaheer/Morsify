BASE_MORSE = {
    # Uppercase letters
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.',
    'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.',
    'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-',
    'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--', 'Z': '--..',
    # Lowercase letters
    'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.', 'g': '--.',
    'h': '....', 'i': '..', 'j': '.---', 'k': '-.-', 'l': '.-..', 'm': '--', 'n': '-.',
    'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.', 's': '...', 't': '-', 'u': '..-',
    'v': '...-', 'w': '.--', 'x': '-..-', 'y': '-.--', 'z': '--..',
    # Numbers
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    # Punctuation
    '.': '.-.-.-', ',': '--..--', '?': '..--..', '!': '-.-.--', '/': '-..-.',
    '(': '-.--.', ')': '-.--.-', '&': '.-...', ':': '---...', ';': '-.-.-.',
    '=': '-...-', '+': '.-.-.', '-': '-....-', '_': '..--.-', '"': '.-..-.',
    '$': '...-..-', '@': '.--.-.', ' ': '/'
}

# reverse mapping
REVERSE_MORSE = {v: k for k, v in BASE_MORSE.items()}

def encode_to_morse_plus(text: str):
    out = []
    for char in text:
        if char in BASE_MORSE:
            if char.isupper():
                out.append('.-.-')  # Special marker for uppercase
                out.append(BASE_MORSE[char.lower()])
            else:
                out.append(BASE_MORSE[char])
        elif char == ' ':
            out.append('/')
        else:
            out.append('..--..')  # Unknown character
    return ' '.join(out)

def decode_from_morse_plus(morse_text: str):
    """
    Convert morse back to text with original case preserved.
    """
    parts = morse_text.split(' ')
    decoded = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == '/':
            decoded.append(' ')
        elif p == '.-.-' and i + 1 < len(parts):
            next_char = parts[i + 1]
            if next_char in REVERSE_MORSE:
                decoded.append(REVERSE_MORSE[next_char].upper())
                i += 1
            else:
                decoded.append('?')
        elif p in REVERSE_MORSE:
            decoded.append(REVERSE_MORSE[p])
        else:
            decoded.append('?')
        i += 1
    return ''.join(decoded)