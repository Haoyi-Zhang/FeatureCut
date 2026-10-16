"""Vector drawing primitives; copied into each independent project generator."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)

def obligations(out):
    d=Drawing((-1,-2.6,9,1.5))
    for n,x,y,w,h,label,ds in [('g',0,.6,1.1,.9,'$g\\in C$',False),('a',2.3,.6,1.7,1.1,'$a\\notin C$\n$t_a\\geq11$',False),('x',4.7,.6,1.5,1.1,'$x:f$\nomitted',False),('z',7.6,.6,2,1.1,'$z_s$\n$\\theta_s=10$',True),('empty',2.3,-1.5,2.8,1.1,"Other source $s'$\nempty prefix",False),('zp',7.6,-1.5,2,1.1,"$z_{s'}$\nseal $t>10$",True)]:
        d.box(n,x,y,w,h,label,dashed=ds)
    for a,b,ds in [('g','a',False),('a','x',False),('x','z',True),('empty','zp',True)]:d.edge(a,b,sa='e',sb='w',dashed=ds)
    d.text(5.4,-1.1,'no observed tail',size=8)
    d.save(out,'obligations')

def hardness(out):
    d=Drawing((-1,-2.7,8.5,2.1))
    nodes={'g':(0,0),'a':(2.2,1),'b':(2.2,-1),'x':(4.6,1.5),'y':(4.6,0),'z':(4.6,-1.5),'xx':(7.1,1.5),'yy':(7.1,0),'zz':(7.1,-1.5)}
    labels=dict(zip(nodes,['$g$','$a_1$','$a_2$','$x_1$','$x_2$','$x_3$','$z_1$','$z_2$','$z_3$']))
    for n,(x,y) in nodes.items():d.box(n,x,y,.72,.72,labels[n],shape='circle',dashed=n in ('xx','yy','zz'))
    d.ax.add_patch(Circle((0,0),.44,fill=False,linewidth=.55,zorder=2))
    for a,b in [('g','a'),('g','b'),('a','x'),('a','y'),('b','y'),('b','z')]:d.edge(a,b,sa='e',sb='w')
    for a,b in [('x','xx'),('y','yy'),('z','zz')]:d.edge(a,b,sa='e',sb='w',dashed=True)
    for x,s in [(0,'$L_g=0$'),(2.2,'$L_{a_j}=1$'),(4.6,'$L_{x_i}=0$'),(7.1,'$\\theta=0$')]:d.text(x,-2.3,s)
    d.save(out,'hardness')

def intervals(out):
    d=Drawing((-1.3,-4.9,7.2,1))
    for i,x in enumerate([0,2,4,6],1):
        d.ax.add_patch(Circle((x,0),.055,color='black'));d.text(x,.4,'$o_'+str(i)+'$')
    for y,l,r,s,ds in [(-1,0,2,'$p:2$',False),(-2,2,6,'$q:2$',False),(-3,0,6,'$r:5$',True)]:
        d.line([(l,y),(r,y)],dashed=ds)
        for x in (l,r):d.line([(x,y-.13),(x,y+.13)])
        d.text(-.7,y,s)
    for n,x,s in [('a',0,'$0$'),('b',3,'$2$'),('c',6,'$4$')]:d.box(n,x,-4.25,.6,.6,s,shape='circle')
    d.edge('a','b',sa='e',sb='w');d.edge('b','c',sa='e',sb='w')
    d.text(1.5,-3.9,'$p$');d.text(4.5,-3.9,'$q$')
    d.save(out,'intervals')

def scaling(out):
    data=Path(__file__).with_name('scaling.dat').read_text(encoding='utf-8').splitlines()
    rows=[dict(zip(data[0].split(),s.split(),strict=True)) for s in data[1:] if s.strip()]
    x=[int(r['n']) for r in rows]
    if x != [128,1024,8192]:raise ValueError('Unexpected scale domain')
    fig,ax=plt.subplots(figsize=(3.48,2.7),layout='constrained')
    for key,label,marker,ls in [('shared','Shared','o','-'),('independent','Independent','s','--'),('chains','Chains','^',':')]:
        y=[float(r[key]) for r in rows]
        if any(v<=0 for v in y):raise ValueError('Nonpositive log-scale data')
        ax.plot(x,y,color='black',marker=marker,linestyle=ls,linewidth=.8,markersize=4,label=label)
    ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks(x,labels=[str(v) for v in x])
    ax.set_xlabel('Generator scale');ax.set_ylabel('Forward check (ms)');ax.grid(alpha=.2,linewidth=.4)
    ax.legend(frameon=False,loc='lower center',bbox_to_anchor=(.5,1),ncol=3,fontsize=8,handlelength=1.5,columnspacing=.8)
    fig.savefig(out/'scaling.pdf',metadata={'Creator':'Python Matplotlib','Producer':None,'CreationDate':None,'ModDate':None});plt.close(fig)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    out=parser.parse_args().output;out.mkdir(parents=True,exist_ok=True)
    for draw in (obligations,hardness,intervals,scaling):draw(out)



