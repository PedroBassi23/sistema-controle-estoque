# app.py (versão 2.0)

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# --- CONFIGURAÇÃO ---
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'estoque.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua-chave-secreta-super-segura'

db = SQLAlchemy(app)

# --- MODELOS DO BANCO DE DADOS ---

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    quantidade_estoque = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5)

    def to_dict(self):
        """Converte o objeto Produto para um dicionário, útil para JSON."""
        return {
            'id': self.id,
            'codigo': self.codigo,
            'nome': self.nome,
            'categoria': self.categoria,
            'preco': self.preco,
            'quantidade_estoque': self.quantidade_estoque,
            'estoque_minimo': self.estoque_minimo
        }

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id', ondelete='CASCADE'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    data = db.Column(db.DateTime, default=func.now())
    produto = db.relationship('Produto', backref=db.backref('movimentacoes', lazy=True, cascade="all, delete-orphan"))

# --- CONTEXT PROCESSOR (para ter as categorias em todas as páginas) ---
@app.context_processor
def inject_categorias():
    # Pega todas as categorias únicas do banco de dados para popular o menu
    categorias_tuplas = db.session.query(Produto.categoria).distinct().all()
    categorias = [c[0] for c in categorias_tuplas] # Converte lista de tuplas em lista de strings
    return dict(categorias_menu=categorias)

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    produtos = Produto.query.order_by(Produto.nome).all()
    alertas_estoque = [p for p in produtos if p.quantidade_estoque <= p.estoque_minimo]
    
    # Dados para os cards do dashboard
    total_produtos = len(produtos)
    total_itens_estoque = db.session.query(func.sum(Produto.quantidade_estoque)).scalar() or 0

    return render_template('index.html', 
                           produtos=produtos, 
                           alertas_estoque=alertas_estoque,
                           total_produtos=total_produtos,
                           total_itens_estoque=total_itens_estoque)

@app.route('/categoria/<nome_categoria>')
def pagina_categoria(nome_categoria):
    produtos_da_categoria = Produto.query.filter_by(categoria=nome_categoria).order_by(Produto.nome).all()
    return render_template('categoria.html', produtos=produtos_da_categoria, nome_categoria=nome_categoria)

# --- ROTAS DE CRUD DE PRODUTOS ---

@app.route('/produto/novo', methods=['POST'])
def novo_produto():
    # Verifica se o código do produto já existe
    codigo_existente = Produto.query.filter_by(codigo=request.form['codigo']).first()
    if codigo_existente:
        flash(f"Erro: O código '{request.form['codigo']}' já está cadastrado!", 'danger')
        return redirect(url_for('index'))

    novo = Produto(
        codigo=request.form['codigo'],
        nome=request.form['nome'],
        categoria=request.form['categoria'],
        preco=float(request.form['preco']),
        quantidade_estoque=int(request.form['quantidade_estoque']),
        estoque_minimo=int(request.form['estoque_minimo'])
    )
    db.session.add(novo)
    db.session.commit()
    flash('Produto cadastrado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/produto/editar/<int:id>', methods=['POST'])
def editar_produto(id):
    produto = Produto.query.get_or_404(id)
    
    # Pega o código do formulário
    novo_codigo = request.form['codigo']
    
    # Verifica se o novo código já existe em OUTRO produto
    codigo_existente = Produto.query.filter(Produto.codigo == novo_codigo, Produto.id != id).first()
    if codigo_existente:
        flash(f"Erro: O código '{novo_codigo}' já pertence a outro produto!", 'danger')
        return redirect(url_for('index'))

    produto.codigo = novo_codigo
    produto.nome = request.form['nome']
    produto.categoria = request.form['categoria']
    produto.preco = float(request.form['preco'])
    produto.quantidade_estoque = int(request.form['quantidade_estoque'])
    produto.estoque_minimo = int(request.form['estoque_minimo'])
    
    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/produto/excluir/<int:id>', methods=['POST'])
def excluir_produto(id):
    produto = Produto.query.get_or_404(id)
    db.session.delete(produto)
    db.session.commit()
    flash(f'O produto "{produto.nome}" foi excluído com sucesso.', 'success')
    return redirect(url_for('index'))

@app.route('/produto/dados/<int:id>', methods=['GET'])
def get_dados_produto(id):
    """ Rota API para pegar dados do produto para o modal de edição """
    produto = Produto.query.get_or_404(id)
    return jsonify(produto.to_dict())

# --- ROTAS DE MOVIMENTAÇÃO E RELATÓRIO ---

@app.route('/movimentar', methods=['POST'])
def movimentar_estoque():
    produto_id = int(request.form['produto_id'])
    tipo = request.form['tipo_movimentacao']
    quantidade = int(request.form['quantidade'])
    produto = Produto.query.get_or_404(produto_id)

    if tipo == 'entrada':
        produto.quantidade_estoque += quantidade
        flash(f'{quantidade} unidades de "{produto.nome}" adicionadas ao estoque.', 'success')
    elif tipo == 'saida':
        if produto.quantidade_estoque >= quantidade:
            produto.quantidade_estoque -= quantidade
            flash(f'{quantidade} unidades de "{produto.nome}" removidas do estoque.', 'info')
        else:
            flash(f'Estoque insuficiente para "{produto.nome}". Apenas {produto.quantidade_estoque} disponíveis.', 'danger')
            return redirect(request.referrer or url_for('index')) # Volta para a página anterior

    movimentacao = Movimentacao(produto_id=produto_id, tipo=tipo, quantidade=quantidade)
    db.session.add(movimentacao)
    db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/relatorio')
def relatorio():
    movimentacoes = Movimentacao.query.order_by(Movimentacao.data.desc()).all()
    return render_template('relatorio.html', movimentacoes=movimentacoes)

# --- INICIALIZAÇÃO ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)