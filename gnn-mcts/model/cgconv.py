import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Linear
from torch.nn import Sequential as Seq
from torch_geometric.nn.conv import MessagePassing


class CGConv(MessagePassing):
    r"""The crystal graph convolutional operator from the
    `"Crystal Graph Convolutional Neural Networks for an
    Accurate and Interpretable Prediction of Material Properties"
    <https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.120.145301>`_
    paper

    .. math::
        \mathbf{x}^{\prime}_i = \mathbf{x}_i + \sum_{j \in \mathcal{N}(i)}
        \sigma \left( \mathbf{z}_{i,j} \mathbf{W}_f + \mathbf{b}_f \right)
        \odot g \left( \mathbf{z}_{i,j} \mathbf{W}_s + \mathbf{b}_s  \right)

    where :math:`\mathbf{z}_{i,j} = [ \mathbf{x}_i, \mathbf{x}_j,
    \mathbf{e}_{i,j} ]` denotes the concatenation of central node features,
    neighboring node features and edge features.
    In addition, :math:`\sigma` and :math:`g` denote the sigmoid and softplus
    functions, respectively.

    Args:
        channels (int): Size of each input sample.
        dim (int): Edge feature dimensionality.
        aggr (string, optional): The aggregation operator to use
            (:obj:`"add"`, :obj:`"mean"`, :obj:`"max"`).
            (default: :obj:`"add"`)
        bias (bool, optional): If set to :obj:`False`, the layer will not learn
            an additive bias. (default: :obj:`True`)
        **kwargs (optional): Additional arguments of
            :class:`torch_geometric.nn.conv.MessagePassing`.
    """

    def __init__(self, channels, dim, aggr='add', bias=True, **kwargs):
        super(CGConv, self).__init__(aggr=aggr, **kwargs)
        self.in_channels = channels
        self.out_channels = channels
        self.dim = dim

        self.lin_f = Linear(2 * channels + dim, channels, bias=bias)
        self.lin_s = Linear(2 * channels + dim, channels, bias=bias)

        self.reset_parameters()

    def reset_parameters(self):
        self.lin_f.reset_parameters()
        self.lin_s.reset_parameters()

    def forward(self, x, edge_index, edge_attr):
        """"""
        return self.propagate(edge_index, x=x, edge_attr=edge_attr)

    def message(self, x_i, x_j, edge_attr):
        z = torch.cat([x_i, x_j, edge_attr], dim=-1)
        return self.lin_f(z).sigmoid() * F.softplus(self.lin_s(z))

    def update(self, aggr_out, x):
        return aggr_out + x

    def __repr__(self):
        return '{}({}, {}, dim={})'.format(self.__class__.__name__,
                                           self.in_channels, self.out_channels,
                                           self.dim)


class CGConvLayer(MessagePassing):
    def __init__(self, node_channels, edge_channels, out_channels, aggr='add'):
        super(CGConvLayer, self).__init__()
        self.node_channels = node_channels
        self.edge_channels = edge_channels
        self.out_channels = out_channels

        self.aggr = aggr
        # self.mlp = Seq(nn.ReLU(), nn.Linear(out_channels, out_channels), nn.BatchNorm1d(out_channels), nn.ReLU(),
        #                nn.Linear(out_channels, out_channels), nn.BatchNorm1d(out_channels), nn.ReLU())
        self.mlp = nn.ReLU()
        self.cg_conv = CGConv(self.node_channels, self.edge_channels, aggr=self.aggr)

    def forward(self, node_attr, edge_index, edge_attr):
        return self.mlp(self.cg_conv(node_attr, edge_index, edge_attr))


class GNN(nn.Module):
    def __init__(self, node_dim, edge_dim, embed_dim, layer):
        super(GNN, self).__init__()
        self.layer = layer
        self.mlp = Seq(nn.Linear(node_dim, embed_dim), nn.BatchNorm1d(embed_dim), nn.ReLU())
        # Layers
        self.gnn_layers = nn.ModuleList()
        for _ in range(layer):
            self.gnn_layers.append(CGConvLayer(embed_dim, edge_dim, embed_dim))

    def forward(self, node_attr, edge_index, edge_attr):
        for i in range(self.layer):
            node_attr = self.mlp(node_attr) if i == 0 else node_attr
            node_attr = self.gnn_layers[i](node_attr, edge_index, edge_attr)

        return node_attr
