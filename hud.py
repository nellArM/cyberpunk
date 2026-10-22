"""2D overlay drawn with pygame.font and uploaded as a texture when its content changes."""
import moderngl
import pygame

FONT_NAMES = "microsoftjhenghei,microsoftjhengheiui,microsoftyahei,simhei,notosanscjktc,arialunicodems,arial"


class Hud:
    def __init__(self, ctx, size):
        self.size = size
        self.surf = pygame.Surface(size, pygame.SRCALPHA)
        self.tex = ctx.texture(size, 4)
        self.tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        s = max(0.75, size[1] / 900.0)
        self.font = pygame.font.SysFont(FONT_NAMES, int(21 * s))
        self.small = pygame.font.SysFont(FONT_NAMES, int(17 * s))
        self.big = pygame.font.SysFont(FONT_NAMES, int(46 * s), bold=True)
        self.scale = s
        self._key = None

    def _text(self, font, text, color, pos, anchor="topleft"):
        img = font.render(text, True, color)
        shadow = font.render(text, True, (0, 0, 0))
        rect = img.get_rect(**{anchor: pos})
        self.surf.blit(shadow, rect.move(2, 2))
        self.surf.blit(img, rect)
        return rect

    def update(self, info, altitude_frac, top_label, prompt, banner, banner_color, help_lines, debug_lines, aim="",
               map_view=None, mission=None, title=None):
        """top_label: what the top of the altimeter stands for (the shown tower's top floor);
        aim: grapple range readout next to the crosshair; map_view: callable(surf, (font, small), scale)
        that draws the full-screen city map instead of the HUD (redrawn every call);
        mission: [(text, color)] for the box at the top center; title: lines of the start screen
        (continue / new game), drawn over everything else."""
        if map_view is not None:
            self._key = None
            self.surf.fill((0, 0, 0, 0))
            map_view(self.surf, (self.font, self.small), self.scale)
            if prompt:
                w, h = self.size
                r = self._text(self.font, prompt, (230, 250, 255), (w // 2, int(h * 0.94)), "center")
                pygame.draw.rect(self.surf, (0, 220, 255, 120), r.inflate(int(24 * self.scale), int(12 * self.scale)),
                                 1, border_radius=4)
            self.tex.write(pygame.image.tobytes(self.surf, "RGBA", True))
            return
        key = (tuple(info), round(altitude_frac, 3), top_label, prompt, banner, banner_color, tuple(help_lines),
               tuple(debug_lines), aim, tuple(mission or ()), tuple(title or ()))
        if key == self._key:
            return
        self._key = key
        w, h = self.size
        s = self.scale
        surf = self.surf
        surf.fill((0, 0, 0, 0))
        if title:
            self._title(title)
            self.tex.write(pygame.image.tobytes(surf, "RGBA", True))
            return

        # status panel
        lh = int(28 * s)
        panel = pygame.Rect(int(16 * s), int(16 * s), int(360 * s), int(18 * s) + lh * len(info))
        pygame.draw.rect(surf, (6, 8, 22, 150), panel, border_radius=6)
        pygame.draw.rect(surf, (0, 220, 255, 200), panel, 2, border_radius=6)
        for i, (text, color) in enumerate(info):
            self._text(self.font, text, color, (panel.x + int(12 * s), panel.y + int(9 * s) + i * lh))

        # altimeter bar on the right edge
        top, bot = int(h * 0.15), int(h * 0.85)
        x = w - int(46 * s)
        pygame.draw.line(surf, (0, 220, 255, 160), (x, top), (x, bot), 2)
        for k in range(11):
            yy = bot - (bot - top) * k // 10
            pygame.draw.line(surf, (0, 220, 255, 160), (x - 6, yy), (x + 6, yy), 1)
        self._text(self.small, top_label, (0, 220, 255), (x + 10, top), "midleft")
        self._text(self.small, "1F", (0, 220, 255), (x + 10, bot), "midleft")
        ym = bot - int((bot - top) * max(0.0, min(1.0, altitude_frac)))
        pygame.draw.polygon(surf, (255, 60, 200, 230), [(x - 18, ym - 7), (x - 18, ym + 7), (x - 6, ym)])

        # crosshair (yellow ring + distance when the grapple can catch something)
        pygame.draw.circle(surf, (255, 255, 255, 170), (w // 2, h // 2), max(2, int(2 * s)))
        if aim and aim != "—":
            pygame.draw.circle(surf, (255, 215, 80, 200), (w // 2, h // 2), int(9 * s), 1)
            self._text(self.small, aim, (255, 215, 80), (w // 2 + int(14 * s), h // 2), "midleft")

        if mission:
            lh3 = int(26 * s)
            width = max(self.font.size(t)[0] for t, _ in mission) + int(32 * s)
            mp = pygame.Rect(0, 0, width, int(16 * s) + lh3 * len(mission))
            mp.midtop = (w // 2, int(14 * s))
            pygame.draw.rect(surf, (10, 8, 22, 170), mp, border_radius=6)
            pygame.draw.rect(surf, (255, 200, 60, 210), mp, 2, border_radius=6)
            for i, (text, color) in enumerate(mission):
                self._text(self.font, text, color, (mp.centerx, mp.y + int(8 * s) + i * lh3 + lh3 // 2), "center")

        hp = None
        if help_lines:                                  # help / menu panel at the bottom left
            lh2 = int(24 * s)
            width = max(self.small.size(line)[0] for line in help_lines) + int(28 * s)
            hp = pygame.Rect(0, 0, max(int(560 * s), width), int(20 * s) + lh2 * len(help_lines))
            hp.bottomleft = (int(16 * s), h - int(16 * s))

        if banner:
            self._text(self.big, banner, banner_color, (w // 2, int(h * 0.26)), "center")
        if prompt:
            y = int(h * 0.80)
            if hp is not None:                          # keep it above the panel instead of under it
                y = min(y, hp.top - int(28 * s))
            r = self._text(self.font, prompt, (230, 250, 255), (w // 2, y), "center")
            pygame.draw.rect(surf, (0, 220, 255, 120), r.inflate(int(24 * s), int(12 * s)), 1, border_radius=4)

        if hp is not None:
            pygame.draw.rect(surf, (6, 8, 22, 165), hp, border_radius=6)
            pygame.draw.rect(surf, (255, 60, 200, 200), hp, 2, border_radius=6)
            for i, line in enumerate(help_lines):
                self._text(self.small, line, (235, 235, 255), (hp.x + int(12 * s), hp.y + int(10 * s) + i * lh2))

        for i, line in enumerate(debug_lines):
            self._text(self.small, line, (180, 255, 180), (w - int(16 * s), int(16 * s) + i * int(22 * s)),
                       "topright")

        self.tex.write(pygame.image.tobytes(surf, "RGBA", True))

    def _title(self, lines):
        """Start screen: dimmed city behind a panel; lines[0] is the heading."""
        w, h = self.size
        s = self.scale
        surf = self.surf
        surf.fill((4, 5, 12, 150))
        lh = int(34 * s)
        width = max([self.font.size(t)[0] for t in lines[1:]] + [self.big.size(lines[0])[0]]) + int(80 * s)
        box = pygame.Rect(0, 0, width, int(110 * s) + lh * (len(lines) - 1))
        box.center = (w // 2, h // 2)
        pygame.draw.rect(surf, (6, 8, 22, 225), box, border_radius=10)
        pygame.draw.rect(surf, (255, 60, 200, 230), box, 2, border_radius=10)
        self._text(self.big, lines[0], (0, 230, 255), (box.centerx, box.y + int(48 * s)), "center")
        for i, text in enumerate(lines[1:]):
            color = (255, 215, 80) if text.startswith("[") else (255, 120, 120) if text.startswith("!") else (225, 232, 250)
            self._text(self.font, text.lstrip("!"), color, (box.centerx, box.y + int(100 * s) + i * lh), "center")
