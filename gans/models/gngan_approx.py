import torch
import torch.nn as nn
import random

class GradNorm(nn.Module):
    def __init__(self, *modules):
        super(GradNorm, self).__init__()
        self.main = nn.Sequential(*modules)

    def forward(self, x):
        x.requires_grad_(True)
        fx = self.main(x)

        # batch shuffle
        b_shuff = list(range(x.shape[0]))
        random.shuffle(b_shuff)
        x_shuffle = x[ b_shuff, : ]

        approx_fx = self.main(x_shuffle)


        grad_norm = torch.norm(torch.abs( (x - x_shuffle) ).view(x.size(0), -1), dim=1)
        grad_norm = grad_norm.view(-1, *[1 for _ in range(len(fx.shape) - 1)])

        approx_grad_x = torch.abs((fx - approx_fx)) / grad_norm
        approx_grad_x = torch.norm(approx_grad_x.view(approx_grad_x.size(0), -1), dim=1)

        fx = fx / (approx_grad_x+1e-12)
        # grad_norm = torch.norm(approx_grad_x.view(approx_grad_x.size(0), -1), dim=1)
        # grad_norm = grad_norm.view(-1, *[1 for _ in range(len(fx.shape) - 1)])
        # fx = (fx / (grad_norm + 1e-12 ) )
        return fx


class NormalizeGradients(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x):
        return x

    @staticmethod
    def backward(ctx, grad):
        # print(grad.shape)
        norm = (grad * grad).sum(dim=[1, 2, 3], keepdim=True).sqrt()
        norm = torch.abs(norm * grad.shape[0])
        # print(norm.shape, norm)
        return grad / (norm + 1e-7)


class Generator(nn.Module):
    def __init__(self, z_dim, M=4):
        super().__init__()
        self.z_dim = z_dim
        self.M = M
        self.linear = nn.Linear(self.z_dim, M * M * 512)
        self.main = nn.Sequential(
            nn.ConvTranspose2d(
                512, 256, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(True),
            nn.ConvTranspose2d(
                256, 128, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(True),
            nn.ConvTranspose2d(
                128, 64, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(True),
            nn.Conv2d(64, 3, kernel_size=3, stride=1, padding=1, bias=False),
            nn.Tanh())
        weights_init(self)

    def forward(self, z):
        x = self.linear(z)
        x = x.view(x.size(0), -1, self.M, self.M)
        x = self.main(x)
        return x


class Discriminator(nn.Module):
    def __init__(self, M=32):
        super().__init__()
        self.M = M

        self.main = nn.Sequential(
            # M
            nn.Conv2d(
                3, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(
                64, 64, kernel_size=4, stride=2, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            # M / 2
            nn.Conv2d(
                64, 128, kernel_size=3, stride=1, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(
                128, 128, kernel_size=4, stride=2, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            # M / 4
            nn.Conv2d(
                128, 256, kernel_size=3, stride=1, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(
                256, 256, kernel_size=4, stride=2, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True),
            # M / 8
            nn.Conv2d(
                256, 512, kernel_size=3, stride=1, padding=1, bias=False),
            nn.LeakyReLU(0.1, inplace=True))

        self.linear = nn.Linear(M // 8 * M // 8 * 512, 1, bias=False)
        weights_init(self)

    def forward(self, x):
        x = self.main(x)
        x = torch.flatten(x, start_dim=1)
        x = self.linear(x)
        return x


class Generator32(Generator):
    def __init__(self, z_dim):
        super().__init__(z_dim, M=4)


class Generator48(Generator):
    def __init__(self, z_dim):
        super().__init__(z_dim, M=6)


class Discriminator32(Discriminator):
    def __init__(self):
        super().__init__(M=32)


class Discriminator48(Discriminator):
    def __init__(self):
        super().__init__(M=48)


class ResGenBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.residual = nn.Sequential(
            nn.BatchNorm2d(in_channels),
            nn.ReLU(),
            nn.Upsample(scale_factor=2),
            nn.Conv2d(in_channels, out_channels, 3, stride=1, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(),
            nn.Conv2d(out_channels, out_channels, 3, stride=1, padding=1),
        )
        self.shortcut = nn.Sequential(
            nn.Upsample(scale_factor=2),
            nn.Conv2d(in_channels, out_channels, 1, stride=1, padding=0)
        )

    def forward(self, x):
        return self.residual(x) + self.shortcut(x)


class ResGenerator32(nn.Module):
    def __init__(self, z_dim):
        super().__init__()
        self.z_dim = z_dim
        self.linear = nn.Linear(z_dim, 4 * 4 * 256)

        self.blocks = nn.Sequential(
            ResGenBlock(256, 256),
            ResGenBlock(256, 256),
            ResGenBlock(256, 256),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.Conv2d(256, 3, 3, stride=1, padding=1),
            nn.Tanh(),
        )
        weights_init(self)

    def forward(self, z):
        inputs = self.linear(z)
        inputs = inputs.view(-1, 256, 4, 4)
        return self.blocks(inputs)


class ResGenerator48(nn.Module):
    def __init__(self, z_dim):
        super().__init__()
        self.z_dim = z_dim
        self.linear = nn.Linear(z_dim, 6 * 6 * 512)

        self.blocks = nn.Sequential(
            ResGenBlock(512, 256),
            ResGenBlock(256, 128),
            ResGenBlock(128, 64),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.Conv2d(64, 3, 3, stride=1, padding=1),
            nn.Tanh(),
        )
        weights_init(self)

    def forward(self, z):
        inputs = self.linear(z)
        inputs = inputs.view(-1, 512, 6, 6)
        return self.blocks(inputs)


class OptimizedResDisblock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.shortcut = nn.Sequential(
            nn.AvgPool2d(2),
            nn.Conv2d(in_channels, out_channels, 1, 1, 0))
        self.residual = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, 1, 1),
            nn.ReLU(),
            nn.Conv2d(out_channels, out_channels, 3, 1, 1),
            nn.AvgPool2d(2))

    def forward(self, x):
        return self.residual(x) + self.shortcut(x)


class ResDisBlock(nn.Module):
    def __init__(self, in_channels, out_channels, down=False):
        super().__init__()
        shortcut = []
        if in_channels != out_channels or down:
            shortcut.append(
                nn.Conv2d(in_channels, out_channels, 1, 1, 0))
        if down:
            shortcut.append(nn.AvgPool2d(2))
        self.shortcut = nn.Sequential(*shortcut)

        residual = [
            nn.ReLU(),
            nn.Conv2d(in_channels, out_channels, 3, 1, 1),
            nn.ReLU(),
            nn.Conv2d(out_channels, out_channels, 3, 1, 1),
        ]
        if down:
            residual.append(nn.AvgPool2d(2))
        self.residual = nn.Sequential(*residual)

    def forward(self, x):
        return (self.residual(x) + self.shortcut(x))


class ResDiscriminator32(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            OptimizedResDisblock(3, 128),
            ResDisBlock(128, 128, down=True),
            ResDisBlock(128, 128),
            ResDisBlock(128, 128),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)))
        self.linear = nn.Linear(128, 1)
        weights_init(self)

    def forward(self, x):
        x = self.model(x)
        x = torch.flatten(x, start_dim=1)
        x = self.linear(x)
        return x


class ResDiscriminator48(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = nn.Sequential(
            OptimizedResDisblock(3, 64),
            ResDisBlock(64, 128, down=True),
            ResDisBlock(128, 256, down=True),
            ResDisBlock(256, 512, down=True),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)))
        self.linear = nn.Linear(512, 1)
        weights_init(self)

    def forward(self, x):
        x = self.model(x).sum(dim=[2, 3])
        x = torch.flatten(x, start_dim=1)
        x = self.linear(x)
        return x


def weights_init(m):
    modules = (torch.nn.Conv2d, torch.nn.ConvTranspose2d)
    for param in m.modules():
        if isinstance(param, modules):
            torch.nn.init.kaiming_normal_(param.weight.data)
            if param.bias is not None:
                torch.nn.init.zeros_(param.bias.data)
