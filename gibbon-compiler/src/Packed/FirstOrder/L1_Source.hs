{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DeriveFunctor #-}
{-# LANGUAGE NamedFieldPuns #-}
{-# LANGUAGE PatternSynonyms #-}
{-# OPTIONS_GHC -Wall #-}

-- | The source language for recursive tree traversals.
--   This is a first-order language for the "closed world" scenario:
--   not integrating with a functional host language, but rather
--   genarating C code like a DSL.

module Packed.FirstOrder.L1_Source
    (
     -- * Core types
      Prog(..), DDef(..), FunDefs, FunDef(..), Exp(..), progToEnv

      -- * Primitive operations
    , Prim(..), primArgsTy

      -- * Types and helpers
    , Ty, Ty1(..), pattern Packed, pattern SymTy
    , voidTy, hasPacked, sizeOf, TyCur(..)

    -- * Expression and Prog helpers
    , freeVars, subst, substE, mapExprs, getFunTy

      -- * Trivial expressions
    , assertTriv, assertTrivs, isTriv, hasTimeIt
    , projNonFirst, mkProj, mkProd, mkProdTy, mkLets

      -- * Examples
    , add1Prog
    )
    where

import Packed.FirstOrder.Common
import Data.Map as M
import Data.Set as S
import Data.List as L
import GHC.Generics
import Text.PrettyPrint.GenericPretty
import Control.DeepSeq (NFData)

--------------------------------------------------------------------------------

-- | Complete programs include datatype definitions:
--
-- For evaluating a complete program, main's type will be an Int or a
-- datatype.  For running a pass benchmark, main will be Nothing and
-- we will expect a "benchmark" function definition which consumes an
-- appropriate packed AST datatype.
data Prog = Prog { ddefs    :: DDefs Ty
                 , fundefs  :: FunDefs Ty Exp
                 , mainExp  :: Maybe Exp
                 }
  deriving (Read,Show,Eq,Ord, Generic, NFData)

-- | Abstract some of the differences of top level program types, by
--   having a common way to extract an initial environment.
progToEnv :: Prog -> Env2 (Ty1 ())
progToEnv Prog{fundefs} =
    Env2 M.empty
         (M.fromList [ (n,(fmap (\_->()) a, fmap (\_->()) b))
                     | FunDef n (_,a) b _ <- M.elems fundefs ])


-- | The source language.  It has pointer based sums and products, as
-- well as packed algebraic datatypes.
data Exp = VarE Var
         | LitE Int
         | AppE Var Exp -- Only apply top-level / first-order functions
         | PrimAppE Prim [Exp]
         | LetE (Var,Ty,Exp) Exp
          -- ^ One binding at a time, but could bind a tuple for
          -- mutual recursion.
         | IfE Exp Exp Exp
         | ProjE Int Exp
         | MkProdE [Exp]
         | CaseE Exp [(DataCon, [Var], Exp)]
           -- ^ Case on a PACKED datatype.
         | MkPackedE DataCon [Exp]
         | TimeIt Exp Ty Bool -- The boolean indicates this TimeIt is really (iterate _)

           -- Limited list handling:
         | MapE  (Var,Ty,Exp) Exp
         | FoldE { initial  :: (Var,Ty,Exp)
                 , iterator :: (Var,Ty,Exp)
                 , body     :: Exp }
  deriving (Read,Show,Eq,Ord, Generic, NFData)

-- | Some of these primitives are (temporarily) tagged directly with
-- their return types.
data Prim = AddP | SubP | MulP -- ^ May need more numeric primitives...
          | EqSymP          -- ^ Equality on Sym
          | EqIntP       -- ^ Equality on Int
          | DictInsertP Ty  -- ^ takes dict, k,v; annotated with element type
          | DictLookupP Ty  -- ^ takes dict,k errors if absent; annotated with element type
          | DictEmptyP Ty   -- ^ annotated with element type to avoid ambiguity
          | ErrorP String Ty
              -- ^ crash and issue a static error message.
              --   To avoid needing inference, this is labeled with a return type.

--          | GetLoc Var
--          | AddLoc Int Var
          | SizeParam

          | MkTrue -- ^ Zero argument constructor.
          | MkFalse -- ^ Zero argument constructor.

          | MkNullCursor -- ^ Zero argument constructor.
          | ReadPackedFile (Maybe FilePath) TyCon Ty
            -- ^ Read (mmap) a binary file containing packed data.  This must be annotated with the
            -- type of the file being read.  The `Ty` tracks the type as the program evolvels
            -- (first PackedTy then CursorTy).  The TyCon tracks the original type name.

-- TODO: Need list construction if we're going to have list:
--          | MkList

  deriving (Read,Show,Eq,Ord, Generic, NFData)

instance Out Prim
instance Out TyCur
instance Out a => Out (Ty1 a)
-- Do this manually to get prettier formatting:
-- instance Out Ty where  doc x = __

instance Out Exp
instance Out Prog

-- type TEnv = Map Var Ty

-- TEMP/FIXME: leaving out these for now.
pattern SymTy = IntTy

type Ty = Ty1 ()

pattern Packed c = PackedTy c () NoneCur

-- | Types include boxed/pointer-based products as well as unpacked
-- algebraic datatypes.  This data is parameterized to allow
-- annotation later on.
data Ty1 a =
          IntTy
--        | SymTy -- ^ Symbols used in writing compiler passes.
--                --   It's an alias for Int, an index into a symbol table.
        | BoolTy
        | ProdTy [Ty1 a]               -- ^ An N-ary tuple
        | SymDictTy (Ty1 a)            -- ^ A map from SymTy to Ty
        | PackedTy DataCon a TyCur     -- ^ No type arguments to TyCons for now.
          -- ^ We allow built-in dictionaries from symbols to a value type.
        | ListTy (Ty1 a)               -- ^ These are not fully first class.  They are onlyae
                                       -- allowed as the fields of data constructors.
  deriving (Show, Read, Ord, Eq, Generic, NFData, Functor)

data TyCur = NoneCur -- ^ Ordinary packed ty, with no fancy annotation
           -- For fancy cursor types, is it enough to have lists of types? 
           | HasCur [Ty1 ()] -- ^ Has(..)
           | NeedsCur [Ty1 ()] -- ^ Needs(..)
  deriving (Show, Read, Ord, Eq, Generic, NFData)

voidTy :: Ty
voidTy = ProdTy []

-- | Do values of this type contain packed data?
hasPacked :: Ty1 a -> Bool
hasPacked t = case t of
                PackedTy{} -> True
                ProdTy ls -> any hasPacked ls
                SymTy     -> False
                BoolTy    -> False
                IntTy     -> False
                SymDictTy ty -> hasPacked ty
                ListTy _     -> error "FINISHLISTS"

-- | Provide a size in bytes, if it is statically known.
sizeOf :: Ty1 a -> Maybe Int
sizeOf t = case t of
             PackedTy{}  -> Nothing
             ProdTy ls   -> sum <$> mapM sizeOf ls
             SymDictTy _ -> Just 8 -- Always a pointer.
             IntTy       -> Just 8
             BoolTy      -> sizeOf IntTy
             ListTy _    -> error "FINISHLISTS"

-- | Transform the expressions within a program.
mapExprs :: (Exp -> Exp) -> Prog -> Prog
mapExprs fn prg@Prog{fundefs,mainExp} =
  prg{ fundefs = fmap (fmap fn) fundefs
     , mainExp = fmap fn mainExp }


--------------------------------------------------------------------------------

-- | Look up the input/output type of a top-level function binding.
getFunTy :: Var -> Prog -> (Ty,Ty)
getFunTy fn Prog{fundefs} =
    case M.lookup fn fundefs of
      Just FunDef{funArg=(_vr,argty), funRetTy} -> (argty,funRetTy)
      Nothing -> error $ "getFunTy: L1 program does not contain binding for function: "++show fn

-- | Free data variables.  Does not include function variables, which
-- currently occupy a different namespace.
freeVars :: Exp -> S.Set Var
freeVars ex =
  case ex of
    VarE v -> S.singleton v
    LitE _ -> S.empty
    AppE _v e -> freeVars e  -- S.insert v (freeVars e)
    PrimAppE _ ls -> S.unions (L.map freeVars ls)
    LetE (v,_,rhs) bod -> freeVars rhs `S.union`
                          S.delete v (freeVars bod)
    ProjE _ e -> freeVars e
    CaseE e ls -> S.union (freeVars e)
                  (S.unions $ L.map (\(_, _, ee) -> freeVars ee) ls)
    MkProdE ls     -> S.unions $ L.map freeVars ls
    MkPackedE _ ls -> S.unions $ L.map freeVars ls
    TimeIt e _ _ -> freeVars e
    IfE a b c -> freeVars a `S.union` freeVars b `S.union` freeVars c
    MapE (v,_t,rhs) bod -> freeVars rhs `S.union`
                           S.delete v (freeVars bod)
    FoldE (v1,_t1,r1) (v2,_t2,r2) bod ->
        freeVars r1 `S.union` freeVars r2 `S.union`
        (S.delete v1 $ S.delete v2 $ freeVars bod)


subst :: Var -> Exp -> Exp -> Exp
subst old new ex =
  let go = subst old new in
  case ex of
    VarE v | v == old  -> new
           | otherwise -> VarE v
    LitE _          -> ex
    AppE v e        -> AppE v (go e)
    PrimAppE p ls   -> PrimAppE p $ L.map go ls
    LetE (v,t,rhs) bod | v == old  -> LetE (v,t,go rhs) bod
                       | otherwise -> LetE (v,t,go rhs) (go bod)

    ProjE i e  -> ProjE i (go e)
    CaseE e ls -> CaseE (go e) (L.map (\(c,vs,er) -> (c,vs,go er)) ls)
    MkProdE ls     -> MkProdE $ L.map go ls
    MkPackedE k ls -> MkPackedE k $ L.map go ls
    TimeIt e t b -> TimeIt (go e) t b
    IfE a b c -> IfE (go a) (go b) (go c)
    MapE (v,t,rhs) bod | v == old  -> MapE (v,t, rhs)    (go bod)
                       | otherwise -> MapE (v,t, go rhs) (go bod)
    FoldE (v1,t1,r1) (v2,t2,r2) bod ->
        let r1' = if v1 == old then r1 else go r1
            r2' = if v2 == old then r2 else go r2
        in FoldE (v1,t1,r1') (v2,t2,r2') (go bod)

-- | Expensive subst that looks for a whole matching sub-EXPRESSION.
--   If the old expression is a variable, this still avoids going under binder.s
substE :: Exp -> Exp -> Exp -> Exp
substE old new ex =
  let go = substE old new in
  case ex of
    _ | ex == old -> new
    VarE v          -> VarE v
    LitE _          -> ex
    AppE v e        -> AppE v (go e)
    PrimAppE p ls   -> PrimAppE p $ L.map go ls
    LetE (v,t,rhs) bod | (VarE v) == old  -> LetE (v,t,go rhs) bod
                       | otherwise -> LetE (v,t,go rhs) (go bod)

    ProjE i e  -> ProjE i (go e)
    CaseE e ls -> CaseE (go e) (L.map (\(c,vs,er) -> (c,vs,go er)) ls)
    MkProdE ls     -> MkProdE $ L.map go ls
    MkPackedE k ls -> MkPackedE k $ L.map go ls
    TimeIt e t b -> TimeIt (go e) t b
    IfE a b c -> IfE (go a) (go b) (go c)
    MapE (v,t,rhs) bod | VarE v == old  -> MapE (v,t, rhs)    (go bod)
                       | otherwise -> MapE (v,t, go rhs) (go bod)
    FoldE (v1,t1,r1) (v2,t2,r2) bod ->
        let r1' = if VarE v1 == old then r1 else go r1
            r2' = if VarE v2 == old then r2 else go r2
        in FoldE (v1,t1,r1') (v2,t2,r2') (go bod)



primArgsTy :: Prim -> [Ty]
primArgsTy p =
  case p of
    AddP -> [IntTy, IntTy]
    SubP -> [IntTy, IntTy]
    MulP -> [IntTy, IntTy]
    EqSymP  -> [SymTy, SymTy]
    EqIntP  -> [IntTy, IntTy]
    MkTrue  -> []
    MkFalse -> []
    MkNullCursor -> []
    SizeParam    -> []
    DictEmptyP _ty -> []
    DictInsertP _ty -> error "primArgsTy: dicts not handled yet"
    DictLookupP _ty -> error "primArgsTy: dicts not handled yet"
    ReadPackedFile{} -> []
    (ErrorP _ _) -> []


--------------------------------------------------------------------------------

-- Simple invariant assertions:

assertTriv :: Exp -> a -> a
assertTriv e =
  if isTriv e
  then id
  else error$ "Expected trivial argument, got: "++sdoc e

assertTrivs :: [Exp] -> a -> a
assertTrivs [] = id
assertTrivs (a:b) = assertTriv a . assertTrivs b

isTriv :: Exp -> Bool
isTriv e =
   case e of
     VarE _ -> True
     LitE _ -> True
     -- These should really turn to literalS:
     PrimAppE MkTrue  [] -> True
     PrimAppE MkFalse [] -> True
     ----------------- POLICY DECISION ---------------
     -- Leave these as trivial for now:
     ProjE _ et | isTriv et -> True
     MkProdE ls -> all isTriv ls
     _  -> False

-- | Does the expression contain a TimeIt form?
hasTimeIt :: Exp -> Bool
hasTimeIt rhs =
    case rhs of
      TimeIt _ _ _ -> True
      MkPackedE _ _ -> False
      VarE _        -> False
      LitE _        -> False
      AppE _ _      -> False
      PrimAppE _ _ -> False
      ProjE _ e    -> hasTimeIt e
      MkProdE ls   -> any hasTimeIt ls
      IfE a b c -> hasTimeIt a || hasTimeIt b || hasTimeIt c
      CaseE _ ls -> any hasTimeIt [ e | (_,_,e) <- ls ]
      LetE (_,_,e1) e2 -> hasTimeIt e1 || hasTimeIt e2
      MapE (_,_,e1) e2 -> hasTimeIt e1 || hasTimeIt e2
      FoldE (_,_,e1) (_,_,e2) e3 -> hasTimeIt e1 || hasTimeIt e2 || hasTimeIt e3

-- | Project something which had better not be the first thing in a tuple.
projNonFirst :: Int -> Exp -> Exp
projNonFirst 0 e = error $ "projNonFirst: expected nonzero index into expr: "++sdoc e
projNonFirst i e = ProjE i e

-- | Project position K of N, unless (K,N) = (0,1) in which case no
-- projection is necessary.
mkProj :: (Eq a, Num a) => Int -> a -> Exp -> Exp
mkProj 0 1 e = e
mkProj ix _ e = ProjE ix e

-- | Make a product type while avoiding unary products.
mkProd :: [Exp]-> Exp
mkProd [e] = e
mkProd ls = MkProdE ls

-- | Same as mkProd, at the type level
mkProdTy :: [Ty]-> Ty
mkProdTy [t] = t
mkProdTy ls = ProdTy ls

-- | Make a nested series of lets.
mkLets :: [(Var,Ty,Exp)] -> Exp -> Exp
mkLets [] bod = bod
mkLets (b:bs) bod = LetE b (mkLets bs bod)



--------------------------------------------------------------------------------

treeTy :: Ty
treeTy = Packed "Tree"

add1Prog :: Prog
add1Prog = Prog (fromListDD [DDef (toVar "Tree") [ ("Leaf",[IntTy])
                                                 , ("Node",[Packed "Tree", Packed "Tree"])]])
                (M.fromList [(toVar "add1",exadd1)])
                Nothing

exadd1 :: FunDef Ty Exp
exadd1 = FunDef (toVar "add1") (toVar "tr",treeTy) treeTy exadd1Bod

exadd1Bod :: Exp
exadd1Bod =
    CaseE (VarE (toVar "tr")) $
      [ ("Leaf", [toVar "n"], PrimAppE AddP [VarE (toVar "n"), LitE 1])
      , ("Node", [toVar "x",toVar "y"], MkPackedE "Node"
                             [ AppE (toVar "add1") (VarE $ toVar "x")
                             , AppE (toVar "add1") (VarE $ toVar "y")])
      ]
