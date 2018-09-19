
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################
        # file to edit: dev_nb/006a_unet.ipynb

from nb_006 import *
import gc

def in_channels(m):
    for l in flatten_model(m):
        if hasattr(l, 'weight'): return l.weight.shape[1]
    raise Exception('No weight layer')

def model_sizes(m, size=(256,256), full=True):
    hooks = hook_outputs(m)
    ch_in = in_channels(m)
    x = torch.zeros(1,ch_in,*size)
    x = m.eval()(x)
    res = [o.stored.shape for o in hooks]
    if not full: hooks.remove()
    return res,x,hooks if full else res

def get_sfs_idxs(sizes, last=True):
    if last:
        feature_szs = [size[-1] for size in sizes]
        sfs_idxs = list(np.where(np.array(feature_szs[:-1]) != np.array(feature_szs[1:]))[0])
        if feature_szs[0] != feature_szs[1]: sfs_idxs = [0] + sfs_idxs
    else: sfs_idxs = list(range(len(sfs)))
    return sfs_idxs

class UnetBlock(nn.Module):
    def __init__(self, up_in_c, x_in_c, hook):
        super().__init__()
        self.hook = hook
        ni = up_in_c
        self.upconv = conv2d_trans(ni, ni//2) # H, W -> 2H, 2W
        ni = ni//2 + x_in_c
        self.conv1 = conv2d(ni, ni//2)
        ni = ni//2
        self.conv2 = conv2d(ni, ni)
        self.bn = nn.BatchNorm2d(ni)

    def forward(self, up_in):
        up_out = self.upconv(up_in)
        cat_x = torch.cat([up_out, self.hook.stored], dim=1)
        x = F.relu(self.conv1(cat_x))
        x = F.relu(self.conv2(x))
        return self.bn(x)

class DynamicUnet(nn.Sequential):
    def __init__(self, encoder, n_classes, last=True):
        imsize = (256,256)
        sfs_szs,x,self.sfs = model_sizes(encoder, size=imsize)
        sfs_idxs = reversed(get_sfs_idxs(sfs_szs, last))

        ni = sfs_szs[-1][1]
        middle_conv = nn.Sequential(conv2d_relu(ni, ni*2, bn=True), conv2d_relu(ni*2, ni, bn=True))
        x = middle_conv(x)
        layers = [encoder, nn.ReLU(), middle_conv]

        for idx in sfs_idxs:
            up_in_c, x_in_c = int(x.shape[1]), int(sfs_szs[idx][1])
            unet_block = UnetBlock(up_in_c, x_in_c, self.sfs[idx])
            layers.append(unet_block)
            x = unet_block(x)

        ni = unet_block.conv2.out_channels
        if imsize != sfs_szs[0][-2:]: layers.append(conv2d_trans(ni, ni))
        layers.append(conv2d(ni, n_classes, 1))
        super().__init__(*layers)

    def __del__(self):
        if hasattr(self, "sfs"): self.sfs.remove()