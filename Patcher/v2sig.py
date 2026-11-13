"""Ed25519 (RFC 8032) v čisté Pythonu bez závislostí. Podpis patch manifestu: launcher ověří,
že manifest podepsal majitel privátního klíče, takže se do hry nedá podstrčit cizí soubor
ani při průniku na server. Proprietární software (viz LICENSE)."""
import hashlib

_p = 2 ** 255 - 19
_q = 2 ** 252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _sha(b):
    return hashlib.sha512(b).digest()


def _inv(x):
    return pow(x, _p - 2, _p)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_p + 3) // 8, _p)
    if (x * x - xx) % _p != 0:
        x = x * _I % _p
    if x % 2 != 0:
        x = _p - x
    return x


_By = 4 * _inv(5) % _p
_B = (_xrecover(_By) % _p, _By % _p, 1, (_xrecover(_By) * _By) % _p)


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C = 2 * P[3] * Q[3] * _d % _p
    D = 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _enc(P):
    zi = _inv(P[2])
    x, y = P[0] * zi % _p, P[1] * zi % _p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _dec(s):
    if len(s) != 32:
        raise ValueError("bad point")
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _xrecover(y)
    if x & 1 != sign:
        x = _p - x
    P = (x, y, 1, x * y % _p)
    if (-P[0] * P[0] + P[1] * P[1] - 1 - _d * P[0] ** 2 * P[1] ** 2) % _p != 0:
        raise ValueError("point not on curve")
    return P


def _eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _clamp(h):
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    return a | (1 << 254)


def public_key(seed):
    return _enc(_mul(_clamp(_sha(seed)), _B))


def sign(seed, msg):
    h = _sha(seed)
    a = _clamp(h)
    A = _enc(_mul(a, _B))
    r = int.from_bytes(_sha(h[32:] + msg), "little") % _q
    R = _enc(_mul(r, _B))
    k = int.from_bytes(_sha(R + A + msg), "little") % _q
    S = (r + k * a) % _q
    return R + S.to_bytes(32, "little")


def verify(pub, msg, sig):
    try:
        if len(sig) != 64 or len(pub) != 32:
            return False
        A = _dec(pub)
        R = _dec(sig[:32])
        S = int.from_bytes(sig[32:], "little")
        if S >= _q:
            return False
        k = int.from_bytes(_sha(sig[:32] + pub + msg), "little") % _q
        return _eq(_mul(S, _B), _add(R, _mul(k, A)))
    except Exception:
        return False
