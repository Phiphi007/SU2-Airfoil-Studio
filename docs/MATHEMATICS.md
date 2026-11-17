# BCE、D-BCE 与伴随优化数学说明 / Mathematics of BCE, D-BCE and Adjoint Optimization

本文说明软件中“旧 BCE 手调 → 新 D-BCE 优化”的数学关系，并与 CST 对比。符号均以归一化弦长 (x\in[0,1]) 表示。This document derives the manual BCE to D-BCE workflow and compares it with CST, using normalized chord (x\in[0,1]).

## 1. 原始 BCE / Legacy BCE

### 1.1 三条 Bézier 函数 / Three Bézier functions

对任意控制量 (q\in\{h,\alpha,\beta\})，采用 n 阶 Bézier 曲线：

For each control quantity (q\in\{h,\alpha,\beta\}), use an n-th order Bézier curve:

$$
q(t)=\sum_{i=0}^{n}B_i^n(t)q_i,
\qquad
B_i^n(t)=\binom{n}{i}(1-t)^{n-i}t^i.
$$

控制点横坐标可采用前缘加密映射

The control-point abscissae may use a leading-edge clustering map

$$
x_i=\left(\frac{i}{n}\right)^\gamma,
$$

而当前软件在网格/拟合阶段优先使用余弦采样，以避免额外优化变量 (gamma) 带来的尺度病态。The current fitting and meshing stages prefer cosine sampling, avoiding an additional poorly scaled exponent (gamma).

### 1.2 局部椭圆族 / Family of local ellipses

记 (alpha,\beta) 为弧度，定义

With (alpha,\beta) in radians, define

$$
D=\cos^2\beta-\sin^2\alpha,
$$

$$
y_c=\frac{h\sin\alpha\cos\alpha}{D},\qquad
r_y=\frac{h\sin\beta\cos\beta}{D},\qquad
r_x=\left|\frac{h\sin\beta}{\sqrt{D}}\right|.
$$

在每个中心 (X) 上构造椭圆

At each center (X), construct

$$
\left(\frac{x-X}{r_x}\right)^2+
\left(\frac{y-y_c}{r_y}\right)^2=1.
$$

其上、下弧为

Its upper and lower arcs are

$$
y_\pm(x;X)=y_c\pm r_y\sqrt{1-\left(\frac{x-X}{r_x}\right)^2}.
$$

翼型由包络得到：

The airfoil is the envelope:

$$
y_u(x)=\sup_X y_+(x;X),\qquad
y_l(x)=\inf_X y_-(x;X).
$$

最后将几何前后缘仿射归一化到 `[0,1]`。The final geometry is affinely normalized between leading and trailing edges.

### 1.3 优点与条件数问题 / Strengths and conditioning limits

`h,α,β` 具有直观的设计含义，因此原始 BCE 很适合人工拖点。但用于梯度优化时存在三类困难：The parameters are intuitive for manual editing, but gradient optimization faces three issues:

1. 三角函数和分母 (D) 强耦合，接近 (D=0) 时敏感度放大。Trigonometric coupling amplifies sensitivities near (D=0).
2. `sup/inf` 的包络控制椭圆会切换，Jacobian 仅分段光滑。Envelope ownership switches, so the Jacobian is only piecewise smooth.
3. 不同控制点对几何的尺度和作用范围差异很大，形成近共线列。Columns have different scales and can become nearly collinear.

这并不否定 BCE 的价值：它更像交互式生成器，而不是直接作为高维优化坐标。This does not invalidate BCE; it is better regarded as an interactive generator than a raw high-dimensional optimization coordinate system.

## 2. D-BCE：紧支撑光滑笔刷 / D-BCE: compact smooth brushes

### 2.1 基函数 / Basis function

对中心 (c) 和半宽 (w>0)，定义标准 bump：

For center (c) and half-width (w>0), define

$$
\phi_{c,w}(x)=
\begin{cases}
\exp\!\left(1-\dfrac{1}{1-s^2}\right), & |s|<1,\\
0, & |s|\ge1,
\end{cases}
\qquad s=\frac{x-c}{w}.
$$

归一化使 (phi(c)=1)。在 (x=c\pm w) 处，函数及任意阶导数都为零，因此 (phi\in C^\infty)，且支撑严格限制在 `[c-w,c+w]`。The normalization gives (phi(c)=1). The function and every derivative vanish at the support boundary, so it is (C^\infty) and exactly local.

如需额外端点安全，可乘

For extra endpoint safety, multiply by

$$
e(x)=\sqrt{x}(1-x),
$$

或直接选择不覆盖端点的支撑。Either use this taper or choose supports that exclude the endpoints.

### 2.2 弯度—厚度解耦 / Camber-thickness decoupling

基准上下表面写为

Write the baseline surfaces as

$$
m_0=\frac{y_{u0}+y_{l0}}{2},\qquad
t_0=\frac{y_{u0}-y_{l0}}{2}.
$$

由笔刷系数 (a_j,b_j) 构造

Using brush coefficients (a_j,b_j), define

$$
\delta m(x)=\sum_j a_j\phi_j(x),\qquad
\delta t(x)=\sum_j b_j\phi_j(x).
$$

则

Then

$$
y_u=m_0+t_0+\delta m+\delta t,
$$

$$
y_l=m_0-t_0+\delta m-\delta t.
$$

弯度笔刷使上下表面同向移动；厚度笔刷使上下表面反向移动。A camber brush moves both surfaces together; a thickness brush moves them oppositely.

### 2.3 Jacobian / Geometry Jacobian

离散在 (N) 个弦向点后，几何增量可写为

After discretization at (N) chordwise stations,

$$
\Delta\mathbf y=J\mathbf z,
$$

其中弯度列为 ([\phi_j;\phi_j])，厚度列为 ([\phi_j;-\phi_j])。因此在相同采样和权重下，弯度块与厚度块天然正交：A camber column is ([\phi_j;\phi_j]), while a thickness column is ([\phi_j;-\phi_j]); the two blocks are naturally orthogonal under identical sampling weights:

$$
[\phi;\phi]^T[\psi;-\psi]=0.
$$

同一模式内，过密中心和相似宽度仍会造成列相关。软件因此不一次激活整个字典，而是按梯度投影选取少量笔刷并进行 QR 正交化。Within each mode, dense centers and similar widths can still correlate. The software therefore selects a sparse active set and applies QR orthogonalization.

## 3. 从旧 BCE 到 D-BCE / Legacy BCE to D-BCE handoff

令手调目标与基准之差为

Let the difference between the manual target and baseline be

$$
\Delta m^*=\frac{(y_u^*-y_{u0})+(y_l^*-y_{l0})}{2},
$$

$$
\Delta t^*=\frac{(y_u^*-y_{u0})-(y_l^*-y_{l0})}{2}.
$$

对两个模式分别求带曲率正则的最小二乘：

Solve a curvature-regularized least-squares problem for each mode:

$$
\min_{\mathbf a}
\|W(\Phi\mathbf a-\Delta m^*)\|_2^2+
\lambda\|L\Phi\mathbf a\|_2^2,
$$

$$
\min_{\mathbf b}
\|W(\Phi\mathbf b-\Delta t^*)\|_2^2+
\lambda\|L\Phi\mathbf b\|_2^2,
$$

其中 (W) 可提高前缘权重，(L) 是离散二阶导数。宽度重叠和适度正则可减少窄笔刷相消导致的波浪。Here (W) can emphasize the leading edge and (L) is a discrete second derivative. Overlapping widths and moderate regularization reduce oscillatory cancellation.

零手调增量不需要数值拟合，直接返回基准几何，因此交接误差为机器零。For zero manual change, the baseline is returned directly, giving machine-zero handoff error.

## 4. 与 CST 的关系 / Relation to CST

CST 的典型基为

A typical CST basis is

$$
\psi_i(x)=C(x)\binom{n}{i}x^i(1-x)^{n-i},
\qquad C(x)=\sqrt{x}(1-x).
$$

CST 列在全弦长上有支撑，低阶时条件良好并擅长整体厚度/弯度变化。D-BCE 列局部支撑，适合只修改一个压力敏感区。CST columns have global support and provide well-conditioned low-order global changes; D-BCE columns are local and target a pressure-sensitive region.

| 属性 / Property | CST | D-BCE |
|---|---|---|
| 支撑 / Support | 全局 / global | 紧支撑 / compact |
| 典型维数 / Typical dimension | 低到中 / low-medium | 自适应稀疏 / adaptive sparse |
| 适合 / Best for | 初始全局搜索 / global search | 局部微调 / local refinement |
| 端点 / Endpoints | 由 class function 约束 / class-function controlled | 支撑或端点窗约束 / support or taper |
| 风险 / Risk | 高阶全局振荡 / high-order global oscillation | 相邻窄笔刷相关 / correlated narrow brushes |

因此接力策略通常比“固定相同维数比较”更有工程意义：先用少量 CST 变量找到正确的大尺度区域，再让 D-BCE 只解释剩余局部梯度。A relay is often more meaningful than equal-dimension comparison: low-order CST finds the global basin, then sparse D-BCE captures the remaining local gradient.

## 5. 梯度投影、预条件与稀疏选择 / Gradient projection and conditioning

设离散表面形状梯度为 (mathbf g)，候选几何基矩阵为 (J)。对经尺度归一化并 QR 分解得到的正交基 (Q)，可表示梯度为

For surface gradient (mathbf g), normalize the candidate matrix and compute a QR basis (Q). The representable gradient is

$$
\mathbf g_P=QQ^T\mathbf g.
$$

捕获率定义为

The capture fraction is

$$
\eta=\frac{\|QQ^T\mathbf g\|_2}{\|\mathbf g\|_2}.
$$

(eta) 很低表示当前变量无法表达伴随建议的形变，此时增加迭代步并无意义，应调整模式、中心或尺度。A low (eta) means the active variables cannot represent the adjoint direction; change the mode, centers or widths rather than merely adding iterations.

软件按候选列与残余梯度的归一化内积进行贪心选择：The software greedily selects the candidate with the largest normalized projection on the residual gradient:

$$
j^*=\arg\max_j
\frac{|\phi_j^T\mathbf r|}{\|\phi_j\|_2\|\mathbf r\|_2}.
$$

每次选择后把该方向从残差中投影掉，直到达到激活数或捕获率门槛。After each selection, the represented component is removed until the active-count or capture threshold is reached.

## 6. 信赖域与接受判据 / Trust region and acceptance

令当前目标为 (F_k)，模型预测试步 (mathbf s) 的下降为

Let the local model predict

$$
\Delta F_{\text{pred}}=\nabla F_k^T\mathbf s.
$$

完成 SU2_DEF 和新正问题后得到

After mesh deformation and the corrected direct solve,

$$
\Delta F_{\text{act}}=F(\mathbf x_k+\mathbf s)-F_k,
\qquad
\rho=\frac{\Delta F_{\text{act}}}{\Delta F_{\text{pred}}}.
$$

若 (ho) 足够大且几何/气动约束满足，则接受；否则拒绝并缩小信赖域。较好的模型一致性可扩大半径。A step is accepted when (ho) is sufficient and all constraints pass; otherwise it is rejected and the trust radius shrinks. Strong agreement allows radius expansion.

分块步长可对 CST、弯度笔刷、厚度笔刷和攻角使用不同尺度：Blockwise scaling may be applied to CST, camber brushes, thickness brushes and angle of attack:

$$
\mathbf s=-D^{-1}\widehat{\mathbf g},
\qquad \|D\mathbf s\|_2\le\Delta.
$$

这里 (D) 同时承担单位换算和预条件作用。Here (D) provides both unit scaling and preconditioning.

## 7. 固定攻角与固定升力 / Fixed AoA and fixed lift

固定攻角时直接最小化例如 (C_D)。固定升力时，攻角可视为附加变量，通过小修正满足

At fixed AoA, the objective may be (C_D). At fixed lift, angle of attack is an auxiliary variable corrected to satisfy

$$
c(\mathbf z,\alpha)=C_L(\mathbf z,\alpha)-C_{L,\text{target}}=0.
$$

线性化为

Linearization gives

$$
\frac{\partial C_L}{\partial\alpha}\Delta\alpha
=-
\left(c+\frac{\partial C_L}{\partial\mathbf z}\Delta\mathbf z\right).
$$

攻角修正必须受上下限保护，并通过新的正问题确认；不能只相信线性预测。The angle correction is bounded and must be confirmed by a new direct solve, not by linear prediction alone.

## 8. 几何约束 / Geometry constraints

软件在每个试步至少检查：Every trial checks at least:

$$
t(x)=y_u(x)-y_l(x)\ge t_{\min},
$$

$$
\|\Delta\mathbf y\|_\infty\le d_{\max},
$$

以及前后缘闭合、表面不自交、攻角范围和网格可变形性。It also enforces endpoint closure, non-intersection, angle bounds and mesh deformability.

## 9. 对“更快/更好”的正确解释 / Interpreting “faster” and “better”

D-BCE 并不保证在所有任务上优于 CST。其潜在优势应按达到同等气动改进所需的总成本评价：D-BCE is not universally superior to CST. Its value should be judged by total cost to achieve an equivalent aerodynamic improvement:

$$
\mathcal E=
\frac{\text{accepted objective improvement}}
{T_{\text{adjoint}}+T_{\text{deform}}+T_{\text{direct}}+T_{\text{selection}}}.
$$

还应同时报告成功率、拒绝步数、最终约束裕度、伴随残差和梯度捕获率。变量数不同并非不公平；工程比较的核心是时间、稳健性和最终质量。Report success rate, rejected steps, constraint margin, adjoint convergence and capture fraction as well. Unequal variable counts are acceptable when the comparison targets time, robustness and final quality.
