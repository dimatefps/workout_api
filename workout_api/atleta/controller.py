# workout_api/atleta/controller.py
from datetime import datetime
from fastapi import APIRouter, Body, HTTPException, status, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import joinedload
# removi imports não usados (uuid4, UUID4) para simplificar

from workout_api.atleta.schemas import AtletaIn, AtletaOut, AtletaUpdate, AtletaListOut
from workout_api.atleta.models import AtletaModel
from workout_api.categorias.models import CategoriaModel
from workout_api.centro_treinamento.models import CentroTreinamentoModel
from workout_api.contrib.dependencies import DatabaseDependency

from fastapi_pagination import paginate
from fastapi_pagination.limit_offset import LimitOffsetPage

router = APIRouter()

@router.post(
    '/',
    summary='Criar um novo atleta',
    status_code=status.HTTP_201_CREATED,
    response_model=AtletaOut
)
async def post(
    db_session: DatabaseDependency,
    atleta_in: AtletaIn = Body(...)
):
    categoria_nome = atleta_in.categoria.nome
    ct_nome = atleta_in.centro_treinamento.nome

    categoria = (await db_session.execute(
        select(CategoriaModel).filter_by(nome=categoria_nome))
    ).scalars().first()

    if not categoria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'A categoria {categoria_nome} não foi encontrada.'
        )

    centro_treinamento = (await db_session.execute(
        select(CentroTreinamentoModel).filter_by(nome=ct_nome))
    ).scalars().first()

    if not centro_treinamento:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'O centro de treinamento {ct_nome} não foi encontrado.'
        )

    try:
        atleta_model = AtletaModel(
            **atleta_in.model_dump(exclude={'categoria', 'centro_treinamento'}),
            created_at=datetime.now(),
            categoria_id=categoria.pk_id,
            centro_treinamento_id=centro_treinamento.pk_id,
        )
        db_session.add(atleta_model)
        await db_session.flush()   # garante pk_id
        await db_session.commit()
        await db_session.refresh(atleta_model)

        # Se seu OutMixin está configurado com from_attributes=True,
        # você pode validar direto do ORM:
        return AtletaOut.model_validate(atleta_model, from_attributes=True)

    except IntegrityError:
        await db_session.rollback()
        # status 303 + mensagem exigida
        raise HTTPException(
            status_code=303,
            detail=f"Já existe um atleta cadastrado com o cpf: {atleta_in.cpf}"
        )
    except Exception:
        await db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Ocorreu um erro ao inserir os dados no banco'
        )

@router.get(
    '/',
    summary='Consultar atletas (filtros: nome/cpf) + paginação',
    status_code=status.HTTP_200_OK,
    response_model=LimitOffsetPage[AtletaListOut],  # paginação limit/offset
)
async def query(
    db_session: DatabaseDependency,
    nome: str | None = Query(None, max_length=50, description="Filtro por nome (contém)"),
    cpf: str  | None = Query(None, min_length=11, max_length=11, description="Filtro por CPF (igual)"),
) -> LimitOffsetPage[AtletaListOut]:
    stmt = (
        select(AtletaModel)
        .options(
            joinedload(AtletaModel.categoria),
            joinedload(AtletaModel.centro_treinamento),
        )
    )
    if nome:
        # ilike funciona no Postgres; se for outro SGBD, troque por like/lower(...)
        stmt = stmt.where(AtletaModel.nome.ilike(f"%{nome}%"))
    if cpf:
        stmt = stmt.where(AtletaModel.cpf == cpf)

    atletas = (await db_session.execute(stmt)).scalars().all()

    items = [
        AtletaListOut(
            nome=a.nome,
            categoria=(a.categoria.nome if a.categoria else ""),
            centro_treinamento=(a.centro_treinamento.nome if a.centro_treinamento else ""),
        )
        for a in atletas
    ]
    return paginate(items)  # usa ?limit=&offset=

@router.get(
    '/{id}',
    summary='Consulta um Atleta pelo id',
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def get(id: int, db_session: DatabaseDependency) -> AtletaOut:
    atleta = (
        await db_session.execute(select(AtletaModel).filter_by(pk_id=id))
    ).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}'
        )

    return AtletaOut.model_validate(atleta, from_attributes=True)

@router.patch(
    '/{id}',
    summary='Editar um Atleta pelo id',
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def patch(id: int, db_session: DatabaseDependency, atleta_up: AtletaUpdate = Body(...)) -> AtletaOut:
    atleta = (
        await db_session.execute(select(AtletaModel).filter_by(pk_id=id))
    ).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}'
        )

    data = atleta_up.model_dump(exclude_unset=True)
    try:
        for key, value in data.items():
            setattr(atleta, key, value)

        await db_session.commit()
        await db_session.refresh(atleta)
        return AtletaOut.model_validate(atleta, from_attributes=True)
    except IntegrityError:
        await db_session.rollback()
        raise HTTPException(
            status_code=303,
            detail=f"Já existe um atleta cadastrado com o cpf: {data.get('cpf')}"
        )

@router.delete(
    '/{id}',
    summary='Deletar um Atleta pelo id',
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete(id: int, db_session: DatabaseDependency) -> None:
    atleta = (
        await db_session.execute(select(AtletaModel).filter_by(pk_id=id))
    ).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}'
        )

    await db_session.delete(atleta)
    await db_session.commit()
