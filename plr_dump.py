import sys, struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
key = "h3y_gUyZ".encode("utf-16-le")
data = open(sys.argv[1], "rb").read()
d = Cipher(algorithms.AES(key), modes.CBC(key)).decryptor()
pt = d.update(data) + d.finalize()
print("version", struct.unpack_from("<i", pt, 0)[0], pt[4:11], pt[11])
print(pt[:120].hex(" "))
print(pt[:120])
