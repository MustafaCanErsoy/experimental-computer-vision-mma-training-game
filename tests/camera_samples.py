"""Invented landmark sequences for camera-free regression checks, never recordings."""
from types import SimpleNamespace


def landmarks(extension=0., hidden=None, *, side="left", upward=False):
    image = [SimpleNamespace(x=.5, y=.3, z=0., visibility=.99, presence=.99) for _ in range(33)]
    for i, x, y in ((0, .5, .15), (11, .65, .4), (12, .35, .4), (13, .68, .52),
                    (14, .32, .52), (15, .60, .44), (16, .40, .44), (23, .60, .75), (24, .40, .75)):
        image[i].x, image[i].y = x, y
    world = [SimpleNamespace(x=0., y=0., z=0.) for _ in range(33)]
    if upward:
        image[15 if side == "left" else 16].y -= .225*extension
    for shoulder, elbow, wrist, sign, factor in ((11, 13, 15, 1., extension if side == "left" else 0.),
                                               (12, 14, 16, -1., extension if side == "right" else 0.)):
        s = (.15*sign, 0., 0.)
        w = (.18*sign, -.075, -.12-(0. if upward else .255*factor))
        e = tuple((a+b)/2 for a, b in zip(s, w))
        e = (e[0]+.13*sign*(1-factor), e[1]+.15*(1-factor), e[2])
        for index, xyz in ((shoulder, s), (elbow, e), (wrist, w)):
            world[index].x, world[index].y, world[index].z = xyz
    if hidden is not None:
        image[hidden].visibility = .2
    return image, world


# Two visible samples at extension; a brief hand occlusion on the return.
JAB = ((.25, None), (.55, None), (.90, None), (1., None),
       (.8, 15), (.4, None), (0., None), (0., None), (0., None), (0., None))

# Gradual departure remains in the broad guard region for several frames.
# The visible peak is held rather than still moving at the next sample.
GENTLE_JAB = tuple((factor, None) for factor in (.24, .30, .36, .42, .55, .75, .90, .90)) + (
    (.5, 15), (.2, None), (0., None), (0., None), (0., None), (0., None))
