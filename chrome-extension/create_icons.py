import base64
import zlib
import struct
import os

def create_png(width, height, pixels):
    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = zlib.crc32(chunk) & 0xffffffff
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', crc)
    
    signature = b'\x89PNG\r\n\x1a\n'
    
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr = make_chunk(b'IHDR', ihdr_data)
    
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'
        for x in range(width):
            idx = (y * width + x) * 4
            raw_data += bytes(pixels[idx:idx+4])
    
    compressed = zlib.compress(raw_data, 9)
    idat = make_chunk(b'IDAT', compressed)
    iend = make_chunk(b'IEND', b'')
    
    return signature + ihdr + idat + iend

def create_icon(size):
    pixels = []
    margin = size // 8
    center = size // 2
    
    for y in range(size):
        for x in range(size):
            # Calculate if point is inside lightning bolt
            in_bolt = False
            
            # Simple lightning bolt shape
            # Top part (diagonal from top-right to center)
            if (y >= margin and y < size//2):
                # Line from (center+offset, margin) to (center, size//2)
                expected_x = center + (margin - y) * (size//6) // (size//2 - margin)
                if abs(x - expected_x) < size//8:
                    in_bolt = True
            
            # Bottom part (diagonal from center to bottom-left)
            if (y >= size//2 and y <= size - margin):
                # Line from (center, size//2) to (center-size//6, size-margin)
                expected_x = center - (y - size//2) * (size//6) // (size//2 - margin)
                if abs(x - expected_x) < size//8:
                    in_bolt = True
            
            # Center connector
            if abs(y - size//2) < size//6:
                if abs(x - center) < size//5:
                    in_bolt = True
            
            if in_bolt:
                pixels.extend([80, 238, 222, 255])  # Teal #50eede
            else:
                pixels.extend([19, 19, 21, 255])  # Dark #131315
    
    return create_png(size, size, pixels)

# Create icons
os.makedirs('icons', exist_ok=True)

for size in [16, 48, 128]:
    png_data = create_icon(size)
    filename = f'icons/icon{size}.png'
    with open(filename, 'wb') as f:
        f.write(png_data)
    print(f'Created {filename}')

print('All icons created!')
