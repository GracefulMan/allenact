from core.base_abstractions.experiment_config import ExperimentConfig


class MyConfig(ExperimentConfig):
    MY_VAR: int = 3

    def my_var_is(cls, val):
        assert cls.MY_VAR == val


class MySpecConfig(MyConfig):
    MY_VAR = 6


cfg = MyConfig()
scfg = MySpecConfig()


class TestFrozenAttribs(object):
    def test_frozen_inheritance(self, tmpdir):
        from abc import abstractmethod
        from core.base_abstractions.experiment_config import FrozenClassVariables

        class SomeBase(metaclass=FrozenClassVariables):
            yar = 3

            @abstractmethod
            def use(cls):
                raise NotImplementedError()

        class SomeDerived(SomeBase):
            yar = 33

            def use(cls):
                return cls.yar

        failed = False
        try:
            SomeDerived.yar = 6  # Error
        except Exception as _:
            failed = True
        assert failed

        inst = SomeDerived()
        inst2 = SomeDerived()
        inst.yar = 12  # No error
        assert inst.use() == 12
        assert inst2.use() == 33

    @staticmethod
    def my_func(config, val):
        config.my_var_is(val)

    def test_frozen_experiment_config(self, tmpdir):
        import torch.multiprocessing as mp

        val = 5

        cfg.MY_VAR = val
        cfg.my_var_is(val)
        scfg.MY_VAR = val
        scfg.my_var_is(val)

        failed = False
        try:
            MyConfig.MY_VAR = val
        except RuntimeError:
            failed = True
        assert failed

        failed = False
        try:
            MySpecConfig.MY_VAR = val
        except RuntimeError:
            failed = True
        assert failed

        for fork_method in ["forkserver", "fork"]:
            ctxt = mp.get_context(fork_method)
            p = ctxt.Process(target=self.my_func, kwargs=dict(config=cfg, val=val))
            p.start()
            p.join()
            p = ctxt.Process(target=self.my_func, kwargs=dict(config=scfg, val=val))
            p.start()
            p.join()


if __name__ == "__main__":
    TestFrozenAttribs().test_frozen_inheritance()
    TestFrozenAttribs().test_frozen_experiment_config()
